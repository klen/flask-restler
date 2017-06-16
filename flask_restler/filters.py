"""Support filters."""

import json
import operator

from cached_property import cached_property
from flask import request
from marshmallow import fields, missing, ValidationError
from . import logger


FILTERS_ARG = 'where'


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
        """Initialize filter."""
        self.name = name
        self.fname = fname or name
        self.field = field or fields.Raw(attribute=name)

    def __repr__(self):
        return '<Filter %s>' % (self.field.attribute or self.name or self.fname)

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

    def apply(self, collection, ops, **kwargs):  # noqa
        """Apply current filter."""
        def validator(obj):
            return all(op(obj, val) for (op, val) in ops)
        return [o for o in collection if validator(o)]


class Filters(object):
    """Filters helper."""

    FILTER_CLASS = Filter

    def __init__(self, filters, View):
        """Initialize the helper."""
        self._filters = filters
        self.View = View

    @cached_property
    def filters(self):
        """Prepare filters."""
        if not self._filters:
            return None
        return list(f if isinstance(f, Filter) else self.convert(f) for f in self._filters)

    def convert(self, name):
        """Setup a filter by name."""
        if not self.View.Schema or name not in self.View.Schema._declared_fields:  # noqa
            return self.FILTER_CLASS(name)
        field = self.View.Schema._declared_fields[name]  # noqa
        return self.FILTER_CLASS(name, field=field)

    def filter(self, collection, view, *args, **kwargs):
        """Filter the given collection."""
        request.filters = {}
        data = request.args.get(FILTERS_ARG)
        if not data or self.filters is None:
            return collection

        try:
            data = json.loads(data)
        except (ValueError, TypeError):
            return collection

        logger.debug('Filter resources: %r', data)

        filters = [f for f in self.filters if f.fname in data]
        logger.debug('Filters active: %r', filters)
        for f in filters:
            collection = f.filter(collection, data, view=view, **kwargs)
        return collection
