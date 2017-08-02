"""Support Peewee ORM."""
from __future__ import absolute_import
from peewee import SQL

from .resource import ResourceOptions, Resource, APIError, logger
from .filters import Filter as VanilaFilter, Filters

try:
    from marshmallow_peewee import ModelSchema
except ImportError:
    import logging
    logging.error('Marshmallow-Peewee should be installed to use the integration.')
    raise


def ensure_join(qs, lm, rm, on=None, **join_kwargs):
    """TODO: remove me when problem in Peewee will be fixed."""
    ctx = qs._query_ctx
    for join in qs._joins.get(lm, []):
        if join.dest is rm:
            return qs
    return qs.switch(lm).join(rm, on=on, **join_kwargs).switch(ctx)


class Filter(VanilaFilter):

    """Filter Peewee Collection."""

    operators = VanilaFilter.operators
    operators['$in'] = lambda v, c: v << c
    operators['$nin'] = lambda v, c: ~(v << c)
    operators['$none'] = lambda f, v: f >> v
    operators['$like'] = lambda f, v: f % v
    operators['$ilike'] = lambda f, v: f ** v
    operators['$contains'] = lambda f, v: f.contains(v)
    operators['$starts'] = lambda f, v: f.startswith(v)
    operators['$ends'] = lambda f, v: f.endswith(v)
    operators['$between'] = lambda f, v: f.between(*v)
    operators['$regexp'] = lambda f, v: f.regexp(v)

    list_ops = VanilaFilter.list_ops + ('$between', '$nin')

    mfield = None

    def __init__(self, name, fname=None, field=None, mfield=None):
        """Initialize filter."""
        super(Filter, self).__init__(name, fname, field)
        self.mfield = mfield or self.mfield

    def apply(self, collection, ops, view=None, **kwargs):
        """Filter given Peewee collection."""
        if not self.mfield and view is None:
            return collection

        logger.debug('Apply filter %s (%r)', self.name, ops)

        # Auto join to another collection
        if self.mfield and hasattr(self.mfield, 'model_class') and \
                self.mfield.model_class is not view.meta.model:
            collection = ensure_join(collection, view.meta.model, self.mfield.model_class)

        mfield = self.mfield or view.meta.model._meta.fields.get(self.field.attribute)
        return collection.where(*[op(mfield, val) for op, val in ops])


class ModelFilters(Filters):

    """Filter Peewee Collection."""

    FILTER_CLASS = Filter


class ModelResourceOptions(ResourceOptions):

    """Peewee Resource Options."""

    def __init__(self, cls):
        """Get meta from given model."""
        super(ModelResourceOptions, self).__init__(cls)
        self.name = (self.meta and getattr(self.meta, 'name', None)) or \
            self.model and self.model._meta.db_table or self.name

        if not self.model:
            return None

        if not cls.Schema:
            meta = type('Meta', (object,), dict({'model': self.model}, **self.schema_meta))
            cls.Schema = type(
                self.name.title() + 'Schema', (ModelSchema,), dict({'Meta': meta}, **self.schema))


class ModelResource(Resource):

    """Provide API for Peewee models."""

    OPTIONS_CLASS = ModelResourceOptions

    class Meta:

        """Default options."""

        model = None
        filters_converter = ModelFilters
        schema = {}

    def get_many(self, *args, **kwargs):
        """Setup queryset."""
        return self.meta.model.select()

    def sort(self, collection, *sorting, **Kwargs):
        """Sort resources."""
        logger.debug('Sort collection: %r', sorting)
        sorting_ = []
        for name, desc in sorting:
            field = self.meta.model._meta.fields.get(name) or SQL(name)
            if desc:
                field = field.desc()
            sorting_.append(field)
        if sorting_:
            collection = collection.order_by(*sorting_)
        return collection

    def get_one(self, *args, **kwargs):
        """Load a resource."""
        resource = super(ModelResource, self).get_one(*args, **kwargs)
        if not resource:
            return None

        try:
            resource = self.collection.where(self.meta.model._meta.primary_key == resource).get()
        except self.meta.model.DoesNotExist:
            raise APIError('Resource not found', status_code=404)

        return resource

    def get_schema(self, resource=None, **kwargs):
        """Put resource to schema."""
        return self.Schema(instance=resource)

    def save(self, resource):
        """Save resource to DB."""
        resource.save()
        return resource

    def delete(self, resource=None, **kwargs):
        """Delete a resource."""
        if resource is None:
            raise APIError('Resource not found', status_code=404)
        resource.delete_instance()

    def paginate(self, offset=0, limit=None):
        """Paginate queryset."""
        logger.debug('Paginate collection, offset: %d, limit: %d', offset, limit)
        return self.collection.offset(offset).limit(limit), self.collection.count()

# pylama:ignore=E1102,W0212
