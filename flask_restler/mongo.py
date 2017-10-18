"""Support Mongo DB."""
from types import FunctionType

import bson
import marshmallow as ma
from flask._compat import string_types

from .filters import Filter as VanilaFilter, Filters
from .resource import ResourceOptions, Resource, APIError, logger


class ObjectId(ma.fields.Field):

    """ObjectID Marshmallow Field."""

    def _deserialize(self, value, attr, data):
        try:
            return bson.ObjectId(value)
        except:
            raise ma.ValidationError('invalid ObjectId `%s`' % value)

    def _serialize(self, value, attr, obj):
        if value is None:
            return ma.missing
        return str(value)


class MongoSchema(ma.Schema):

    """Serialize/deserialize results from mongo."""

    _id = ObjectId()

    def __init__(self, instance=None, **kwargs):
        """Initialize the schema."""
        self.instance = instance
        super(MongoSchema, self).__init__(**kwargs)

    @ma.post_load
    def make_instance(self, data):
        """Build object from data."""
        if self.instance is not None:
            self.instance.update(data)
            return self.instance

        return data

    def load(self, data, instance=None, *args, **kwargs):
        """Load data."""
        self.instance = instance or self.instance
        return super(MongoSchema, self).load(data, *args, **kwargs)


class MongoOptions(ResourceOptions):

    """Tune Mongo resource."""

    def __init__(self, cls):
        """Initialize the resource."""
        self._collection = None
        super(MongoOptions, self).__init__(cls)
        self.name = self.meta and getattr(self.meta, 'name', None)
        if not self.collection:
            return

        self.name = self.name or str(self.collection.name)

        if not cls.Schema:
            meta = type('Meta', (object,), self.schema_meta)
            cls.Schema = type(
                self.name.title() + 'Schema', (MongoSchema,), dict({'Meta': meta}, **self.schema))

    @property
    def collection(self):
        """Support lambdas as collection."""
        if isinstance(self._collection, FunctionType):
            return self._collection()
        return self._collection

    @collection.setter
    def collection(self, value):
        """Store initial values."""
        self._collection = value


class Filter(VanilaFilter):

    """Filter Mongo collections."""

    operators = {
        '$eq': '$eq',
        '$ge': '$gte',
        '$gt': '$gt',
        '$in': '$in',
        '$le': '$lte',
        '$lt': '$lt',
        '$ne': '$ne',
        '$nin': '$nin',
    }

    def apply(self, collection, ops, **kwargs):
        """Filter mongo."""
        logger.debug('Apply filter %s (%r)', self.name, ops)
        return collection.find({self.name: dict(ops)})


class MongoFilters(Filters):

    """Converter for Mongo resources."""

    FILTER_CLASS = Filter


class MongoChain(object):

    """Support query chains.

    Only for `find` and `find_one` methods.

    ::

        collection = MongoChain(mongo_collection)
        collection = collection.find({'field': 'value').find('field2': 'value')

        result = collection.find_one({'field3': 'value')
        results = collection.skip(10).limit(10)

    """

    CURSOR_METHODS = (
        'where', 'sort', 'skip', 'rewind', 'retrieved', 'remove_option', 'next', 'min',
        'max_time_ms', 'max_scan', 'max_await_time_ms', 'max', 'limit', 'hint', 'explain',
        'distinct', 'cursor_id', 'count', 'comment', 'collection', 'close', 'clone', 'batch_size',
        'alive', 'address', 'add_option', '__getitem__'
    )

    def __init__(self, collection):
        """Initialize the resource."""
        self.collection = collection
        self.query = []
        self.projection = None
        self.sorting = None

    def find(self, query=None, projection=None):
        """Store filters in self."""
        self.query = self.__update__(query)
        self.projection = projection
        return self

    def find_one(self, query=None, projection=None):
        """Apply filters and return cursor."""
        query = self.__update__(query)
        query = query and {'$and': query} or {}
        logger.debug('Mongo find one: %r', query)
        return self.collection.find_one(query, projection=projection)

    def aggregate(self, pipeline, **kwargs):
        """Aggregate collection."""
        if self.query:
            for params in pipeline:
                if '$match' in params:
                    query = self.__update__(params['$match'])
                    params['$match'] = {'$and': query}
                    break
            else:
                pipeline.insert(0, {'$match': {'$and': query}})
            logger.debug('Mongo aggregate: %r', pipeline)

        if self.sorting:
            pipeline = [p for p in pipeline if '$sort' not in p]
            pipeline.append({'$sort': dict(self.sorting)})

        return self.collection.aggregate(pipeline, **kwargs)

    def sort(self, key, direction=1):
        """Save ordering properties."""
        if isinstance(key, string_types):
            self.sorting = [(key, direction)]
        else:
            self.sorting = key

        return self

    def __repr__(self):
        """String representation."""
        return "<MongoChain (%s) %r>" % (self.collection.name, self.query)

    def __update__(self, query):
        """Update stored query."""
        if query:
            self.query.append(query)

        return self.query

    def __iter__(self):
        """Iterate by self collection."""
        query = self.query and {'$and': self.query} or {}
        if self.sorting:
            return self.collection.find(query, self.projection).sort(self.sorting)

        return self.collection.find(query, self.projection)

    def __getattr__(self, name):
        """Proxy any attributes except find to self.collection."""
        logger.debug('Mongo load: %r', self.query)
        if name in self.CURSOR_METHODS:
            query = self.query and {'$and': self.query} or {}
            cursor = self.collection.find(query, self.projection)
            if self.sorting:
                cursor = cursor.sort(self.sorting)
            return getattr(cursor, name)
        return getattr(self.collection, name)


class MongoResource(Resource):

    """Provide API for Pymongo document and collections."""

    OPTIONS_CLASS = MongoOptions

    class Meta:

        """Default params."""

        collection = None
        filters = 'login',
        filters_converter = MongoFilters
        aggregate = False  # Support aggregation. Set to pipeline.
        object_id = '_id'
        schema = {}

    def get_many(self, *args, **kwargs):
        """Return collection filters."""
        return MongoChain(self.meta.collection)

    def get_one(self, *args, **kwargs):
        """Load a resource."""
        resource = super(MongoResource, self).get_one(*args, **kwargs)
        if not resource:
            return None

        return self.collection.find_one({self.meta.object_id: bson.ObjectId(resource)})

    def paginate(self, offset=0, limit=None):
        """Paginate collection."""
        if self.meta.aggregate:
            pipeline_all = self.meta.aggregate + [{'$skip': offset}, {'$limit': limit}]
            pipeline_num = self.meta.aggregate + [{'$group': {'_id': None, 'total': {'$sum': 1}}}]
            counts = list(self.collection.aggregate(pipeline_num))
            return (
                self.collection.aggregate(pipeline_all),
                counts and counts[0]['total'] or 0
            )
        return self.collection.skip(offset).limit(limit), self.collection.count()

    def to_simple(self, data, many=False, **kwargs):
        """Support aggregation."""
        if isinstance(data, MongoChain) and self.meta.aggregate:
            data = data.aggregate(self.meta.aggregate)
        return super(MongoResource, self).to_simple(data, many=many, **kwargs)

    def get_schema(self, resource=None, **kwargs):
        """Create the resource schema."""
        return self.Schema(instance=resource)  # noqa

    def save(self, resource):
        """Save resource to DB."""
        if resource.get('_id'):
            self.meta.collection.replace_one({'_id': resource['_id']}, resource)
        else:
            write = self.meta.collection.insert_one(resource)
            resource['_id'] = write.inserted_id
        return resource

    def sort(self, collection, *sorting, **Kwargs):
        """Sort resources."""
        sorting = {name: -1 if desc else 1 for name, desc in sorting}
        return collection.sort(list(sorting.items()))

    def delete(self, resource=None, **kwargs):
        """Delete a resource from Mongo collection."""
        if resource is None:
            raise APIError('Resource not found', status_code=404)
        self.collection.delete_one({self.meta.object_id: resource[self.meta.object_id]})
