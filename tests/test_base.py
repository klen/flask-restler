import pytest


def test_app(app, client):
    response = client.get('/')
    assert response.data == b'OK'


def test_resource(app, api, client):
    from flask_restler import Resource

    @api.connect
    class HelloResource(Resource):

        def get(self, resource=None, **kwargs):
            return 'Hello, %s!' % (resource and resource.title() or 'World')

    @api.connect('/hello/<name>/how-are-you')
    class HowAreYouResource(Resource):

        def get(self, resource=None, name=None, **kwargs):
            return 'Hello, %s! How are you?' % name.title()

    response = client.get('/api/v1/hello')
    assert response.json == 'Hello, World!'

    response = client.get('/api/v1/hello/mike')
    assert response.json == 'Hello, Mike!'

    response = client.post('/api/v1/hello')
    assert response.status_code == 405

    response = client.get('/api/v1/hello/mike/how-are-you')
    assert response.json == 'Hello, Mike! How are you?'


def test_resource2(api, client):

    from flask import request
    from flask_restler import route, Resource

    DATA = [1, 2]

    @api.connect
    class SecondResource(Resource):

        methods = 'get', 'post', 'put'

        class Meta:
            name = 'two'
            filters = 'val',
            strict = True

        def get_many(self, **kwargs):
            return DATA

        def post(self, **kwargs):
            DATA.append(request.json)
            return DATA

        def put(self, resource=None, **kwargs):
            resource = int(resource)
            DATA[resource - 1] = request.json
            return DATA

        @route
        def custom(self, **kwargs):
            return self.__class__.__name__

        @route('/custom22/test', methods=['get', 'post'])
        def custom2(self, **kwargs):
            return 'CUSTOM2'

    assert SecondResource.meta.endpoints

    response = client.get('/api/v1/two')
    assert response.json == DATA

    response = client.post_json('/api/v1/two', 3)
    assert response.json == [1, 2, 3]

    response = client.get('/api/v1/two?per_page=2')
    assert response.json == [1, 2]
    assert response.headers['x-page'] == '0'
    assert response.headers['x-page-last'] == '1'

    response = client.get('/api/v1/two?per_page=2&page=1')
    assert response.json == [3]

    response = client.put_json('/api/v1/two/2', 22)
    assert response.json == [1, 22, 3]

    response = client.get('/api/v1/two?where={"val": 22}')
    assert response.json == [22]

    response = client.get('/api/v1/two?where={"val": {"$ge": 3}}')
    assert response.json == [22, 3]

    response = client.get('/api/v1/two/custom')
    assert response.data == b'SecondResource'

    response = client.get('/api/v1/two/custom22/test')
    assert response.data == b'CUSTOM2'

    response = client.post('/api/v1/two/custom22/test')
    assert response.data == b'CUSTOM2'

    response = client.post('/api/v1/two/custom22/test?bla-bla=22')
    assert response.status_code == 400
    assert response.json['error']
    assert SecondResource.meta.strict == set(['where', 'sort', 'page', 'per_page'])


def test_pagination(api, client):
    from flask_restler import Resource

    DATA = list(range(1, 100))

    @api.connect
    class TestResource(Resource):

        class Meta:
            per_page = 20

        def get_many(self, **kwargs):
            return DATA

    response = client.get('/api/v1/test')
    assert len(response.json) == 20

    response = client.get('/api/v1/test?page=2')
    assert len(response.json) == 20
    assert response.json[0] == 41


def test_specs(api, client):
    from flask_restler import Resource, route

    @api.connect
    class HelloResource(Resource):

        @route('/world')
        def world(self, **kwargs):
            return 'Hello, World!'

        def get(self, resource=None, **kwargs):
            return 'Hello, %s!' % (resource and resource.title() or 'World')

    response = client.get('/api/v1/_specs')
    assert response.json
