import logging


__license__ = "MIT"
__project__ = "Flask-Restler"
__version__ = "1.8.1"


logger = logging.getLogger('flask-restler')
logger.addHandler(logging.NullHandler())


class APIError(Exception):

    """Store API exception's information."""

    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['error'] = self.message
        rv['code'] = rv.get('code', self.status_code)
        return rv


def route(rule=None, endpoint=None, **options):
    """Custom routes in resources."""

    def decorator(f):
        endpoint_ = endpoint or f.__name__.lower()
        f.route = (rule, endpoint_, options)
        return f

    if callable(rule):
        rule, f = rule.__name__.lower(), rule
        return decorator(f)

    return decorator

from .api import Api, Resource  # noqa
