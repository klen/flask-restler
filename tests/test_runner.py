import pytest


def test_runner(app, api, client):
    from flask import request
    from flask_restler import Resource, APIError
    from flask_restler.filters import Filter

    data = list(range(10))

    @api.connect
    class TestResource(Resource):

        class Meta:
            filters = Filter('num'),

        def authorize(self, *args, **kwars):
            token = request.args.get('token')
            if not token:
                raise APIError('Forbidden', 403)
            return token

        def get_many(self, *args, **kwargs):
            return data

        def get_one(self, *args, **kwargs):
            """Load resource."""
            resource = kwargs.get(self.meta.name)
            if not resource:
                return None
            return data[resource - 1]

        def post(self, *args, **kwargs):
            return 'POST'

    with pytest.raises(APIError):
        response = api.run(TestResource)

    response = api.run(TestResource, query_string={'token': 1})
    assert response == data

    response = api.run(TestResource, query_string={'token': 1, 'where': {
        'num': {'$ge': 8}
    }})
    assert response == [8, 9]

    response = api.run(TestResource, path='/?token=1', kwargs=dict(test=2))
    assert response == 1

    response = api.run(TestResource, query_string='token=1', method='POST', kwargs=dict(test=2))
    assert response == 'POST'
