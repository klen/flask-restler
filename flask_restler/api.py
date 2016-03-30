from flask import Blueprint, jsonify, request, render_template
import os

from . import APIError
from .auth import current_user

from .resource import Resource
from apispec.ext.marshmallow.swagger import schema2jsonschema


DEFAULT = object()
STATIC = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))
TEMPLATE = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))


class Api(Blueprint):

    """Implement REST API."""

    def __init__(self, name, import_name, specs=True, version="1", url_prefix=None, **kwargs):
        self.version = version
        self.specs = specs

        if not url_prefix and version:
            url_prefix = "/%s" % version

        if self.specs:
            kwargs['static_folder'] = STATIC
            kwargs['static_url_path'] = '/static'
            kwargs['template_folder'] = TEMPLATE

        super(Api, self).__init__(name, import_name, url_prefix=url_prefix, **kwargs)
        self.app = None
        self.resources = []

    def register(self, app, options=None, first_registration=False):
        """Register self to application."""
        self.app = app
        app.errorhandler(APIError)(self.handle_error)
        if self.specs:
            self.route('/_specs')(self.specs_view)

            @self.route('/')
            def specs_html():
                return render_template('swagger.html')

        return super(Api, self).register(app, options or {}, first_registration)

    def authorize(self, *args, **kwargs):
        """Make authorization process.

        The logic could be redifined for each resource.
        """
        return current_user

    def authorization(self, callback):
        """A decorator which helps to update authorize method for current Api."""
        self.authorize = callback
        return callback

    @staticmethod
    def handle_error(error):
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        return response

    def connect(self, resource=None, url=None, url_detail=DEFAULT, **options):
        """Connect resource to the API."""

        api = self

        def wrapper(resource):
            api.resources.append(resource)
            if not issubclass(resource, Resource):
                raise ValueError('Resource should be subclass of api.Resource.')

            url_ = resource.meta.url = url or resource.meta.url or ('/%s' % resource.meta.name)
            view_func = resource.as_view(resource.meta.name, api)
            api.add_url_rule(url_, view_func=view_func, **options)

            for view_, (route_, endpoint_, options_) in resource.meta.endpoints.values():
                api.add_url_rule('%s/%s' % (url_, route_.strip('/')), view_func=view_,
                                 defaults={'endpoint': endpoint_}, **options_)

            url_detail_ = url_detail
            if url_detail is DEFAULT:
                url_detail_ = resource.meta.url_detail = resource.meta.url_detail or \
                    ('%s/<%s>' % (url_, resource.meta.name))

            if url_detail:
                api.add_url_rule(url_detail_, view_func=view_func, **options)

            if api.app is not None:
                return Blueprint.register(api, api.app, {}, False)
            return resource

        if resource is not None and issubclass(resource, Resource):
            return wrapper(resource)

        return wrapper

    def specs_view(self):
        specs = {
            'swagger': '2.0',
            'info': {
                'description': self.__doc__,
                'version': self.version,
                'title': self.name,
            },
            'basePath': self.url_prefix,
            'tags': [],
            'paths': {},
            'definitions': {},
            'host': request.host,
            'schemes': [request.scheme],
        }

        for resource in self.resources:

            if resource.Schema:
                specs['definitions'][resource.meta.name] = schema2jsonschema(resource.Schema)

            specs['tags'].append({
                'name': resource.meta.name,
                'description': resource.__doc__ or resource.__class__.__doc__,
            })
            defaults = {
                'consumes': ['application/json'],
                'produces': ['application/json'],
                'security': [{'api_key': []}],
                'tags': [resource.meta.name],
                'responses': {200: "OK"}
            }

            for endpoint, url in resource.meta.endpoints:
                specs['paths']["%s/%s" % (resource.meta.url, url)] = path = {}
                view = getattr(resource, endpoint)
                path['get'] = dict(summary=view.__doc__, description=view.__doc__, **defaults)
                if hasattr(view, 'specs'):
                    path['get'].update(view.specs)

            specs['paths'][resource.meta.url] = path = {}
            for method in ('get', 'post'):
                if method.upper() not in resource.methods or not hasattr(resource, 'post'):
                    continue
                view = getattr(resource, method)
                path[method] = dict(summary=view.__doc__, description=view.__doc__, **defaults)

                if method == 'post':
                    path[method]['parameters'] = [{
                        'in': 'body',
                        'name': 'body',
                        'description': 'resource body',
                        'required': True,
                        'schema': {
                            '$ref': '#/definitions/%s' % resource.meta.name
                        }
                    }]

                if resource.meta.specs:
                    path[method].update(resource.meta.specs)

            if resource.meta.url_detail:
                url_detail = resource.meta.url_detail.replace('<', '{').replace('>', '}')
                path = specs['paths'][url_detail] = {}
                for method in ('get', 'put', 'delete'):
                    if method.upper() not in resource.methods or not hasattr(resource, 'post'):
                        continue
                    view = getattr(resource, method)
                    path[method] = dict(
                        summary=view.__doc__, description=view.__doc__,
                        parameters=[{
                            'name': resource.meta.name,
                            'in': 'path',
                            'description': 'ID of resource',
                            'type': 'string',
                            'required': True
                        }], **defaults)

                    if method == 'put':
                        path[method]['parameters'].append({
                            'in': 'body',
                            'name': 'body',
                            'description': 'resource body',
                            'required': True,
                            'schema': {
                                '$ref': '#/definitions/%s' % resource.meta.name
                            }
                        })

                if resource.meta.schema_api:
                    path[method].update(resource.meta.schema_api)

        if isinstance(self.specs, dict):
            specs.update(self.specs)

        response = jsonify(specs)
        response.headers.add_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        response.headers.add_header('Access-Control-Allow-Origin', '*')
        response.headers.add_header('Access-Control-Allow-Methods', 'GET,POST,DELETE,PUT')

        return response
