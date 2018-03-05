from __future__ import absolute_import

from types import FunctionType
from sqlalchemy import func

from .filters import Filter as VanilaFilter, Filters
from .resource import ResourceOptions, Resource, APIError, logger


try:
    from sqlalchemy.inspection import inspect
    from marshmallow_sqlalchemy import ModelSchema
except ImportError:
    logger.error('Marshmallow-SQLAlchemy should be installed to use the integration.')
    raise


class Filter(VanilaFilter):

    operators = VanilaFilter.operators
    operators['$in'] = lambda c, v: c.in_(v)
    operators['$nin'] = lambda c, v: ~c.in_(v)

    mfield = None

    def __init__(self, name, fname=None, field=None, mfield=None):
        """Initialize filter.

        :param mfield: Model field
        """
        super(Filter, self).__init__(name, fname, field)
        self.mfield = mfield if mfield is not None else self.mfield

    def apply(self, collection, ops, view=None, **kwargs):
        if self.mfield is not None and view is None:
            return collection

        logger.debug('Apply filter %s (%r)', self.name, ops)

        mfield = self.mfield if self.mfield is not None else getattr(view.meta.model, self.name, None)
        if mfield is None:
            return collection
        collection = collection.filter(*(op(mfield, val) for op, val in ops))
        return collection


class ModelFilters(Filters):

    FILTER_CLASS = Filter


class ModelResourceOptions(ResourceOptions):

    def __init__(self, cls):
        self._session = None
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
            self.primary_key = inspect(self.model).primary_key[0]

        # Flask-SQLAlchemy support
        if not self.session and hasattr(self.model, 'query'):
            self.session = self.model.query.session

    @property
    def session(self):
        """Support lambdas as session."""
        if isinstance(self._session, FunctionType):
            return self._session()
        return self._session

    @session.setter
    def session(self, value):
        """Store initial values."""
        self._session = value


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

    def sort(self, collection, *sorting, **kwargs):
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

        resource = self.collection.filter(self.meta.primary_key == resource).first()
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
        cqs = self.collection.with_entities(func.count()).order_by(None)
        return self.collection.offset(offset).limit(limit), self.meta.session.execute(cqs).scalar()
