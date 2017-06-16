from __future__ import absolute_import

from .filters import Filter as VanilaFilter, Filters
from .resource import ResourceOptions, Resource, APIError


try:
    from sqlalchemy.inspection import inspect
    from marshmallow_sqlalchemy import ModelSchema
except ImportError:
    import logging
    logging.error('Marshmallow-SQLAlchemy should be installed to use the integration.')
    raise


class Filter(VanilaFilter):

    operators = VanilaFilter.operators

    def filter(self, collection, data, view=None, **kwargs):
        ops = self.parse(data)
        prop = getattr(view.meta.model, self.name, None)
        if not prop:
            return collection
        return collection.filter(*(op(prop, val) for op, val in ops))


class ModelFilters(Filters):

    FILTER_CLASS = Filter


class ModelResourceOptions(ResourceOptions):

    def __init__(self, cls):
        super(ModelResourceOptions, self).__init__(cls)
        self.name = (self.meta and getattr(self.meta, 'name', None)) or \
            self.model and self.model.__tablename__ or self.name

        if not self.model:
            return None

        if not cls.Schema:
            meta = type('Meta', (object,), dict({'model': self.model}, **self.schema_meta))
            cls.Schema = type(
                self.name.title() + 'Schema', (ModelSchema,), dict({'Meta': meta}, **self.schema))

        if not self.primary_key:
            col = inspect(self.model).primary_key[0]
            self.primary_key = col.name

        # Flask-SQLAlchemy support
        if not self.session and hasattr(self.model, 'query'):
            self.session = self.model.query.session


class ModelResource(Resource):

    """Provide API for SQLAlchemy models."""

    OPTIONS_CLASS = ModelResourceOptions

    class Meta:
        filters_converter = ModelFilters
        model = None
        primary_key = None
        schema = {}
        session = None

    def get_many(self, *args, **kwargs):
        return self.meta.session.query(self.meta.model).filter()

    def sort(self, collection, *sorting, **Kwargs):
        sorting_ = []
        for name, desc in sorting:
            prop = getattr(self.meta.model, name, None)
            if prop is None:
                continue
            if desc:
                prop = prop.desc()
            sorting_.append(prop)
        if sorting_:
            collection = collection.order_by(*sorting_)
        return collection

    def get_one(self, *args, **kwargs):
        """Load a resource."""
        resource = super(ModelResource, self).get_one(*args, **kwargs)
        if not resource:
            return None

        resource = self.collection.filter_by(**{self.meta.primary_key: resource}).first()
        if resource is None:
            raise APIError('Resource not found', status_code=404)

        return resource

    def get_schema(self, resource=None, **kwargs):
        return self.Schema(session=self.meta.session, instance=resource)

    def save(self, resource):
        """Save resource to DB."""
        self.meta.session.add(resource)
        self.meta.session.commit()
        return resource

    def delete(self, resource=None, **kwargs):
        """Delete a resource."""
        if resource is None:
            raise APIError('Resource not found', status_code=404)
        self.meta.session.delete(resource)
        self.meta.session.commit()

    def paginate(self, offset=0, limit=None):
        """Paginate queryset."""
        return self.collection.offset(offset).limit(limit), self.collection.count()
