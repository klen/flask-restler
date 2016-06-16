import bson
import marshmallow as ma

from .filters import Filter as VanilaFilter, Filters
from .resource import ResourceOptions, Resource, APIError


class ObjectId(ma.fields.Field):

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

    _id = ObjectId()

    def __init__(self, instance=None, **kwargs):
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
        self.instance = instance or self.instance
        return super(MongoSchema, self).load(data, *args, **kwargs)


class MongoOptions(ResourceOptions):

    def __init__(self, cls):
        super(MongoOptions, self).__init__(cls)
        self.name = self.meta and getattr(self.meta, 'name', None)
        if not self.collection:
            return

        self.name = self.name or str(self.collection.name)

        if not cls.Schema:
            meta = type('Meta', (object,), self.schema_meta)
            cls.Schema = type(
                self.name.title() + 'Schema', (MongoSchema,), dict({'Meta': meta}, **self.schema))


class Filter(VanilaFilter):

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

    def filter(self, collection, data, resource=None, **kwargs):
        """Filter mongo."""
        ops = self.parse(data)
        return collection.find({self.name: dict(ops)})


class MongoFilters(Filters):

    FILTER_CLASS = Filter


class MongoChain(object):

    """ Support query chains.

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
        self.collection = collection
        self.query = {}
        self.projection = None

    def find(self, query=None, projection=None):
        self.query = self.__update__(query)
        self.projection = projection
        return self

    def find_one(self, query=None, projection=None):
        self.__update__(query)
        return self.collection.find_one(self.__update__(query), projection=projection)

    def __repr__(self):
        return "<MongoChain (%s) %r>" % (self.collection.name, self.query)

    def __update__(self, query):
        if query:
            return dict(self.query, **query)
        return self.query

    def __getattr__(self, name):
        """Proxy any attributes expept find to self.collection."""
        if name in self.CURSOR_METHODS:
            cursor = self.collection.find(self.query, self.projection)
            return getattr(cursor, name)
        return getattr(self.collection, name)


class MongoResource(Resource):

    """Provide API for Pymongo document and collections."""

    OPTIONS_CLASS = MongoOptions

    class Meta:
        collection = None
        filters = 'login',
        filters_converter = MongoFilters
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
        return self.collection.skip(offset).limit(limit), self.collection.count()

    def get_schema(self, resource=None, **kwargs):
        return self.Schema(instance=resource)

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
        if resource is None:
            raise APIError('Resource not found', status_code=404)
        self.collection.delete_one({self.meta.object_id: resource[self.meta.object_id]})
