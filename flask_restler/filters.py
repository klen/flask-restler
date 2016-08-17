import json
import operator

from cached_property import cached_property
from flask import request
from marshmallow import fields, missing, ValidationError


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

    def __init__(self, name, fname=None, field=None):
        self.name = name
        self.fname = fname or name
        self.field = field or fields.Raw(attribute=name)

    def __repr__(self):
        return '<Filter %s>' % self.field.attribute

    def parse(self, data):
        """Parse operator and value from filter's data."""
        val = data.get(self.fname, missing)
        if not isinstance(val, dict):
            val = self.field.deserialize(val)
            request.filters[self.fname] = val
            return (self.operators['$eq'], val),

        ops = ()
        request.filters[self.fname] = {}
        for op, val in val.items():
            if op not in self.operators:
                continue
            val = self.field.deserialize(val) if op not in self.list_ops else [self.field.deserialize(v) for v in val]  # noqa
            ops += (self.operators[op], val),
            request.filters[self.fname][op] = val

        return ops

    def filter(self, collection, data, **kwargs):
        """Parse data and apply filter."""
        try:
            return self.apply(collection, self.parse(data), **kwargs)
        except ValidationError:
            return collection

    def apply(self, collection, ops, **kwargs):
        """Apply current filter."""
        def validator(obj):
            return all(op(obj, val) for (op, val) in ops)
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

    def filter(self, collection, resource, *args, **kwargs):
        data = request.args.get('where')
        if not data or self.filters is None:
            return collection

        try:
            data = json.loads(data)
        except (ValueError, TypeError):
            return collection

        request.filters = {}
        for f in self.filters:
            if f.fname not in data:
                continue
            collection = f.filter(collection, data, resource=resource, **kwargs)
        return collection
