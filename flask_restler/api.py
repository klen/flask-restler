from __future__ import absolute_import

from flask import Blueprint, jsonify, request, render_template, json
from flask._compat import string_types, PY2
import os
import urllib
import warnings
from inspect import isclass

from . import APIError
from .auth import current_user

from .resource import Resource
from apispec.ext.marshmallow.swagger import schema2jsonschema

if PY2:
    urlencode = urllib.urlencode
else:
    urlencode = urllib.parse.urlencode


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
            def specs_html(): # noqa
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

    def connect(self, *args, **kwargs):
        warnings.warn('The @connect method is depricated, use @route instead.')
        return self.route(*args, **kwargs)

    def route(self, resource=None, url=None, url_detail=DEFAULT, **options):
        """Connect resource to the API."""

        api = self

        def wrapper(res):

            if not isclass(res):
                res = Resource.from_func(res, **options)

            elif not issubclass(res, Resource):
                raise ValueError('Resource should be subclass of api.Resource.')

            api.resources.append(res)

            url_ = res.meta.url = url or res.meta.url or ('/%s' % res.meta.name)
            view_func = res.as_view(res.meta.name, api)
            api.add_url_rule(url_, view_func=view_func, **options)

            for _, (route_, endpoint_, options_) in res.meta.endpoints.values():
                api.add_url_rule('%s/%s' % (url_, route_.strip('/')), view_func=view_func,
                                 defaults={'endpoint': endpoint_}, **options_)

            url_detail_ = url_detail
            if url_detail is DEFAULT:
                url_detail_ = res.meta.url_detail = res.meta.url_detail or \
                    ('%s/<%s>' % (url_, res.meta.name))

            if url_detail:
                api.add_url_rule(url_detail_, view_func=view_func, **options)

            if api.app is not None:
                Blueprint.register(api, api.app, {}, False)

            return res

        if resource is not None and isinstance(resource, type) and issubclass(resource, Resource):
            return wrapper(resource)

        elif isinstance(resource, string_types):
            url = resource

        return wrapper

    def run(self, Resource, path=None, query_string=None, kwargs=None, **rkwargs):
        """Run given resource manually.

        See werkzeug.test.EnvironBuilder for rkwargs.
        """
        resource = Resource(self, raw=True)

        if isinstance(query_string, dict):
            if 'where' in query_string:
                query_string['where'] = json.dumps(query_string['where'])
            query_string = urlencode(query_string)

        rkwargs['query_string'] = query_string
        args = []
        if path:
            args.append(path)
        ctx = self.app.test_request_context(*args, **rkwargs)

        with ctx:
            kwargs = kwargs or {}
            return resource.dispatch_request(**kwargs)

    def specs_view(self, *args, **kwargs):
        specs = {
            'openapi': '3.0.0',
            'info': {
                'title': self.name,
                'description': self.__doc__,
                'version': self.version,
            },
            'basePath': self.url_prefix,
            'tags': [],
            'paths': {},
            'components': {'schemas': {}},
            'host': request.host,
        }

        for resource in self.resources:

            defaults = {
                'consumes': ['application/json'],
                'produces': ['application/json'],
                'security': [{'api_key': []}],
                'tags': [resource.meta.name],
                'responses': {
                    200: {
                        'description': 'OK',
                        'content': {
                            'application/json': {
                            }
                        }
                    }
                }
            }
            if resource.Schema:
                jsonschema = schema2jsonschema(resource.Schema)
                for prop in jsonschema.get('properties', {}).values():
                    if prop.get('type') == 'string' and prop.get('default'):
                        prop['default'] = str(prop['default'])

                specs['components']['schemas'][resource.meta.name] = jsonschema
                defaults['responses'][200]['content']['application/json']['schema'] = {
                    '$ref':  '#/components/schemas/{}'.format(resource.meta.name)
                }

            specs['tags'].append({
                'name': resource.meta.name,
                'description': resource.__doc__ or resource.__class__.__doc__,
            })

            for endpoint, (url_, name_, params_) in resource.meta.endpoints.values():
                specs['paths'][
                    "%s/%s" % (resource.meta.url.rstrip('/'), url_flask_to_swagger(url_))] = path = {}
                path['get'] = dict(
                    summary=endpoint.__doc__,
                    description=endpoint.__doc__,
                    **defaults)
                if hasattr(endpoint, 'specs'):
                    path['get'].update(endpoint.specs)

            specs['paths'][resource.meta.url] = path = {}
            for method in ('get', 'post'):
                if method.upper() not in resource.methods or not hasattr(resource, 'post'):
                    continue
                view = getattr(resource, method)
                path[method] = dict(summary=view.__doc__, description=view.__doc__, **defaults)

                if method == 'post':
                    params = {
                        'in': 'body',
                        'name': 'body',
                        'description': 'resource body',
                        'required': True,
                        'schema': {},
                    }
                    if resource.Schema:
                        params['schema']['$ref'] = '#/components/schemas/{}'.format(
                            resource.meta.name)

                    path[method]['parameters'] = [params]

                if resource.meta.specs:
                    path[method].update(resource.meta.specs)

            if resource.meta.url_detail:
                url_detail = url_flask_to_swagger(resource.meta.url_detail)
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
                        params = {
                            'in': 'body',
                            'name': 'body',
                            'description': 'resource body',
                            'required': True,
                            'schema': {},
                        }
                        if resource.Schema:
                            params['schema']['$ref'] = '#/components/schemas/{}'.format(
                                resource.meta.name)
                        path[method]['parameters'].append(params)

                if resource.meta.specs:
                    path[method].update(resource.meta.specs)

        if isinstance(self.specs, dict):
            specs.update(self.specs)

        return specs


def url_flask_to_swagger(source):
    """Convert Flask URL to swagger path."""
    return source.replace('<', '{').replace('>', '}')
