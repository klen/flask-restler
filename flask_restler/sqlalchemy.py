from .resource import ResourceOptions, Resource, APIError


try:
    from sqlalchemy.inspection import inspect
    from marshmallow_sqlalchemy import ModelSchema
except ImportError:
    import logging
    logging.error('Marshmallow-SQLAlchemy should be installed to use the integration.')
    raise


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
        model = None
        session = None
        primary_key = None
        schema = {}

    def get_many(self, *args, **kwargs):
        return self.meta.session.query(self.meta.model).filter()

    def get_one(self, *args, **kwargs):
        """Load a resource."""
        resource = super(ModelResource, self).get_one(*args, **kwargs)
        if not resource:
            return None

        resource = self.collection.filter_by(**{self.meta.primary_key: resource}).first()
        if resource is None:
            raise APIError('Resource not found', status_code=404)

        return resource

    def get_schema(self, resource=None):
        return self.Schema(session=self.meta.session, instance=resource)

    def save(self, obj):
        self.meta.session.add(obj)
        self.meta.session.commit()

    def delete(self, resource=None, **kwargs):
        """Delete a resource."""
        if resource is None:
            raise APIError('Resource not found', status_code=404)
        self.meta.session.delete(resource)
        self.meta.session.commit()

    def paginate(self, offset=0, limit=None):
        """Paginate queryset."""
        return self.collection.offset(offset).limit(limit), self.collection.count()
