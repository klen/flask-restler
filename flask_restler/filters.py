import json
import operator

from cached_property import cached_property
from flask import request
from marshmallow import fields, missing


class Filter(object):

    """Base filter class."""

    operators = {
        '$lt': operator.lt,
        '$le': operator.le,
        '$gt': operator.gt,
        '$ge': operator.ge,
        '$eq': operator.eq,
        '$ne': operator.ne,
        '$in': lambda v, c: v in c,
    }

    list_ops = '$in',

    def __init__(self, name, fname=None, field=fields.Raw()):
        self.field = field
        self.fname = fname or name
        self.name = name

    def __repr__(self):
        return '<Filter %s>' % self.field.attribute

    def parse(self, data):
        """Parse operator and value from filter's data."""
        val = data.get(self.fname, missing)
        if not isinstance(val, dict):
            return (self.operators['$eq'], self.field.deserialize(val)),

        return tuple(
            (
                self.operators[op],
                (self.field.deserialize(val)) if op not in self.list_ops else [
                    self.field.deserialize(v) for v in val])
            for (op, val) in val.items() if op in self.operators
        )

    def filter(self, collection, data, resource=None, **kwargs):
        ops = self.parse(data)
        validator = lambda obj: all(op(obj, val) for (op, val) in ops)  # noqa
        return [o for o in collection if validator(o)]


class Filters(object):

    FILTER_CLASS = Filter

    def __init__(self, filters, Resource):
        self._filters = filters
        self.Resource = Resource

    @cached_property
    def filters(self):
        if not self._filters:
            return None
        return list(f if isinstance(f, Filter) else self.convert(f) for f in self._filters)

    def convert(self, name):
        if not self.Resource.Schema or name not in self.Resource.Schema._declared_fields:
            return self.FILTER_CLASS(name)
        field = self.Resource.Schema._declared_fields[name]
        return self.FILTER_CLASS(name, field=field)

    def filter(self, collection, *args, **kwargs):
        data = request.args.get('where')
        if not data or self.filters is None:
            return collection

        try:
            data = json.loads(data)
        except (ValueError, TypeError):
            return collection

        for f in self.filters:
            if f.fname not in data:
                continue
            collection = f.filter(collection, data, resource=self.Resource, **kwargs)
        return collection
