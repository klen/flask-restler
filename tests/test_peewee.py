import peewee as pw
from playhouse.db_url import connect


database = connect('sqlite:///:memory:')


class Role(pw.Model):

    name = pw.CharField(255, default='user')

    class Meta:
        database = database


class User(pw.Model):

    login = pw.CharField(255)
    name = pw.CharField(255, null=True)
    password = pw.CharField(127, null=True)

    role = pw.ForeignKeyField(Role, null=True)

    class Meta:
        database = database


database.create_tables([User, Role], safe=True)


def test_resource(app, api, client):
    from flask_restler.peewee import ModelResource

    @api.connect
    class UserResouce(ModelResource):

        methods = 'get', 'post', 'put', 'delete'

        class Meta:
            model = User

    response = client.get('/api/v1/user')
    assert not response.json

    response = client.post_json('/api/v1/user', {
        'login': 'mike',
        'name': 'Mike Bacon',
    })
    assert response.json

    response = client.put_json('/api/v1/user/1', {
        'name': 'David Bacon',
    })
    assert response.json['name'] == 'David Bacon'

    response = client.get('/api/v1/user')
    assert response.json

    response = client.delete('/api/v1/user/1')
    assert not response.json

    response = client.get('/api/v1/user')
    assert not response.json
