from .resource import ResourceOptions, Resource, APIError

try:
    from marshmallow_peewee import ModelSchema
except ImportError:
    import logging
    logging.error('Marshmallow-Peewee should be installed to use the integration.')
    raise


class ModelResourceOptions(ResourceOptions):

    def __init__(self, cls):
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
        model = None
        schema = {}

    def get_many(self, *args, **kwargs):
        return self.meta.model.select()

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
        return self.collection.offset(offset).limit(limit), self.collection.count()
