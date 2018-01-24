"""Base API resource."""

from __future__ import absolute_import

import collections
import math
import logging

from flask import request, current_app, abort, Response
from flask._compat import with_metaclass
from flask.json import dumps
from flask.views import View

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

from . import APIError, logger
from .auth import current_user
from .filters import Filters, FILTERS_ARG


PER_PAGE_ARG = 'per_page'
PAGE_ARG = 'page'
SORT_ARG = 'sort'
INTERNAL_ARGS = set([PER_PAGE_ARG, PAGE_ARG, SORT_ARG, FILTERS_ARG])


class ResourceOptions(object):
    """Prepare resource options."""

    def __init__(self, cls):
        """Initialize resources' options."""
        # Store link to self.meta
        self.meta = meta = getattr(cls, "Meta", None)

        self.cls = cls

        # Inherit meta from parents
        for base in reversed(cls.mro()):
            if not hasattr(base, "Meta"):
                continue

            for k, v in base.Meta.__dict__.items():
                if k.startswith('__'):
                    continue
                setattr(self, k, v)

        # Generate name
        self.name = (meta and getattr(meta, 'name', None)) or \
            cls.__name__.lower().split('resource', 1)[0]

        if self.per_page:  # noqa
            self.per_page = int(self.per_page)

        if self.specs:  # noqa
            self.specs = dict(self.specs)

        if self.strict:  # noqa
            if not isinstance(self.strict, collections.Iterable):
                self.strict = INTERNAL_ARGS
            self.strict = set(self.strict) | INTERNAL_ARGS

        # Setup endpoints
        self.endpoints = getattr(self, 'endpoints', {})
        self.endpoints.update({
            value.route[1]: (value, value.route) for value in cls.__dict__.values()
            if hasattr(value, 'route') and isinstance(value.route, tuple)
        })

        # Setup schema_meta
        self.schema_meta = self.schema_meta or {
            k[7:]: self.__dict__[k] for k in self.__dict__
            if k.startswith('schema_') and not k == 'schema_meta'
        }

        # Setup filters
        self.filters = self.filters_converter(self.filters, cls)

    def __repr__(self):
        return "<Options %s>" % self.cls


class ResourceMeta(type):
    """Do some work for resources."""

    def __new__(mcs, name, bases, params):
        """Initialize class."""
        cls = super(ResourceMeta, mcs).__new__(mcs, name, bases, params)
        cls.methods = set([method.upper() for method in cls.methods])
        cls.meta = cls.OPTIONS_CLASS(cls)
        return cls


class Resource(with_metaclass(ResourceMeta, View)):
    """Base API Resource object."""

    OPTIONS_CLASS = ResourceOptions

    # methods: Allowed methods
    methods = 'get',

    # Schema: Resource marshmallow schema
    Schema = None

    class Meta:
        """Tune the resource."""

        # name: Resource's name (if it is None, it will be calculated)
        name = None

        # per_page: Paginate results (set to None for disable pagination)
        per_page = 100

        # link_header: Add Link header with pagination
        page_link_header = True

        # url: URL for collection, if it is None it will be calculated
        # url_detail: URL for resource detail, if it is None it will be calculated
        url = url_detail = None

        # Resource filters
        filters = ()

        # Define allowed resource sorting params
        sorting = ()

        # Filters converter class
        filters_converter = Filters

        # Strict mode (only allowed query params) set to list of names for allowed query params
        strict = False

        # Swagger specs
        specs = None

        # marshmallow.Schema.Meta options
        # -------------------------------

        # Redefine Schema.Meta completely
        schema_meta = None

    def __init__(self, api=None, raw=False, **kwargs):
        """Initialize the resource."""
        self.api = api
        self.raw = raw
        self.auth = self.collection = None
        super(Resource, self).__init__(**kwargs)

    @classmethod
    def from_func(cls, func, methods=None, **options):

        if methods is None:
            methods = ['GET']

        def proxy(self, *args, **kwargs):
            return func(self, *args, **kwargs)

        params = {m.lower(): proxy for m in methods}
        params['methods'] = methods
        return type(func.__name__, (cls,), params)

    def dispatch_request(self, *args, **kwargs):
        """Process current request."""
        if self.meta.strict and not (self.meta.strict >= set(request.args)):
            raise APIError('Invalid query params.')

        self.auth = self.authorize(*args, **kwargs)
        self.collection = self.get_many(*args, **kwargs)

        kwargs['resource'] = resource = self.get_one(*args, **kwargs)

        endpoint = kwargs.pop('endpoint', None)
        if endpoint and hasattr(self, endpoint):
            method = getattr(self, endpoint)
            logger.debug('Loaded endpoint: %s', endpoint)
            response = method(*args, **kwargs)
            return self.to_json_response(response)

        headers = {}

        if request.method == 'GET' and resource is None:

            # Filter resources
            self.collection = self.filter(self.collection, *args, **kwargs)

            # Sort resources
            if SORT_ARG in request.args:
                sorting = ((name.strip('-'), name.startswith('-'))
                           for name in request.args[SORT_ARG].split(','))
                sorting = ((n, d) for n, d in sorting if n in self.meta.sorting)
                self.collection = self.sort(self.collection, *sorting, **kwargs)

            # Paginate resources
            if self.meta.per_page:
                try:
                    per_page = int(request.args.get(PER_PAGE_ARG, self.meta.per_page))
                    if per_page:
                        page = int(request.args.get(PAGE_ARG, 0))
                        offset = page * per_page
                        self.collection, total = self.paginate(offset, per_page)
                        headers = make_pagination_headers(
                            per_page, page, total, self.meta.page_link_header)
                except ValueError:
                    raise APIError('Pagination params are invalid.')

        if logger.level <= logging.DEBUG:
            logger.debug('Collection: %r', self.collection)
            logger.debug('Params: %r', kwargs)

        try:
            method = getattr(self, request.method.lower())
        except AttributeError:
            return abort(405)

        response = method(*args, **kwargs)
        return self.to_json_response(response, headers=headers)

    def to_json_response(self, response, headers=None):
        """Serialize simple response to Flask response."""
        if self.raw or isinstance(response, Response):
            return response
        response = current_app.response_class(
            dumps(response, indent=2), mimetype='application/json')
        if headers:
            response.headers.extend(headers)
        return response

    def authorize(self, *args, **kwargs):
        """Default authorization method."""
        if self.api is not None:
            return self.api.authorize(*args, **kwargs)
        return current_user

    def get_many(self, *args, **kwargs):
        """Get collection."""
        return []

    def get_one(self, *args, **kwargs):
        """Load resource."""
        return kwargs.get(self.meta.name)

    def get_schema(self, resource=None, **kwargs):
        """Get schema."""
        return self.Schema and self.Schema()  # noqa

    def filter(self, collection, *args, **kwargs):
        """Filter collection."""
        return self.meta.filters.filter(collection, self, *args, **kwargs)

    def sort(self, collection, *sorting, **kwargs):
        """Sort collection."""
        logger.debug('Sort collection: %r', sorting)
        return collection

    def load(self, data, resource=None, **kwargs):
        """Load given data into schema."""
        schema = self.get_schema(resource=resource, **kwargs)
        resource, errors = schema.load(data, partial=resource is not None)
        if errors:
            raise APIError('Bad request', payload={'errors': errors})
        return resource

    def save(self, resource):
        """Create a resource."""
        return resource

    def to_simple(self, data, many=False, **kwargs):
        """Serialize response to simple object (list, dict)."""
        schema = self.get_schema(many=many, **kwargs)
        return schema.dump(data, many=many).data if schema else data

    def paginate(self, offset, limit):
        """Paginate results."""
        logger.debug('Paginate collection, offset: %d, limit: %d', offset, limit)
        return self.collection[offset: offset + limit], len(self.collection)

    def get(self, resource=None, **kwargs):
        """Get resource or collection of resources."""
        logger.debug('Get resources (%r)', resource)
        if resource is not None and resource != '':
            return self.to_simple(resource, resource=resource, **kwargs)

        return self.to_simple(self.collection, many=True, **kwargs)

    def post(self, **kwargs):
        """Create a resource."""
        data = request.json or {}
        resource = self.load(data, **kwargs)
        resource = self.save(resource)
        logger.debug('Create a resource (%r)', kwargs)
        return self.to_simple(resource, **kwargs)

    def put(self, resource=None, **kwargs):
        """Update a resource."""
        logger.debug('Update a resource (%r)', resource)
        if resource is None:
            raise APIError('Resource not found', status_code=404)

        return self.post(resource=resource, **kwargs)

    patch = put

    def delete(self, resource=None, **kwargs):
        """Delete a resource."""
        logger.debug('Delete a resource (%r)', resource)
        if resource is None:
            raise APIError('Resource not found', status_code=404)
        self.collection.remove(resource)


def make_pagination_headers(limit, curpage, total, link_header=True):
    """Return Link Hypermedia Header."""
    lastpage = int(math.ceil(1.0 * total / limit) - 1)
    headers = {'X-Total-Count': str(total), 'X-Limit': str(limit),
               'X-Page-Last': str(lastpage), 'X-Page': str(curpage)}

    if not link_header:
        return headers

    base = "{}?%s".format(request.path)
    links = {}
    links['first'] = base % urlencode(dict(request.args, **{PAGE_ARG: 0}))
    links['last'] = base % urlencode(dict(request.args, **{PAGE_ARG: lastpage}))
    if curpage:
        links['prev'] = base % urlencode(dict(request.args, **{PAGE_ARG: curpage - 1}))
    if curpage < lastpage:
        links['next'] = base % urlencode(dict(request.args, **{PAGE_ARG: curpage + 1}))

    headers['Link'] = ",".join(['<%s>; rel="%s"' % (v, n) for n, v in links.items()])
    return headers


# pylama:ignore=R0201
