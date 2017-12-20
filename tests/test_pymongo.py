from marshmallow import fields
from mongomock import MongoClient

from flask_restler.mongo import MongoResource


DB = MongoClient().db


def test_resource(app, api, client):

    @api.route
    class UserResouce(MongoResource):

        methods = 'get', 'post', 'put', 'delete'

        class Meta:
            collection = DB.user
            sorting = 'login',
            schema = {
                'login': fields.String(),
                'name': fields.String(),
            }

    assert UserResouce.meta.name == 'user'

    response = client.get('/api/v1/user')
    assert not response.json

    response = client.post_json('/api/v1/user', {
        'login': 'mike',
        'name': 'Mike Bacon',
    })
    assert response.json['_id']

    response = client.get('/api/v1/user')
    assert len(response.json) == 1

    _id = response.json[0]['_id']

    response = client.get('/api/v1/user/%s' % _id)
    assert response.json['_id'] == _id

    response = client.put_json('/api/v1/user/%s' % _id, {
        'name': 'Mike Summer',
    })
    assert response.json['_id'] == _id
    assert response.json['name'] == 'Mike Summer'

    response = client.post_json('/api/v1/user', {
        'login': 'dave',
        'name': 'Dave Macaroff',
    })
    assert response.json

    response = client.get('/api/v1/user')
    assert len(response.json) == 2

    response = client.get('/api/v1/user?sort=login,unknown')
    assert response.json[0]['login'] == 'dave'

    response = client.get('/api/v1/user?sort=-login')
    assert response.json[0]['login'] == 'mike'

    response = client.get('/api/v1/user?where={"login": "dave"}')
    assert len(response.json) == 1

    response = client.delete('/api/v1/user/%s' % _id)
    assert not response.json

    response = client.post_json('/api/v1/user', {
        'login': 'dave',
        'name': 'Dave Macaroff',
    })
    assert response.json

    response = client.get('/api/v1/_specs')
    assert response.json

    @api.route('/users', '/users/{user}', endpoint='api-users')
    class UserGroupResouce(MongoResource):

        methods = 'get',

        class Meta:
            collection = lambda: DB.user
            aggregate = [{'$group': {'_id': '$login'}}]

    response = client.get('/api/v1/users?sort=name')
    assert response.status_code == 200
    assert UserGroupResouce.meta.aggregate == [{'$group': {'_id': '$login'}}]
