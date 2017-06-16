import pytest
import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base


Model = declarative_base()


class Role(Model):

    __tablename__ = 'role'

    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String)


class User(Model):

    __tablename__ = 'user'

    id = sa.Column(sa.Integer, primary_key=True)
    login = sa.Column(sa.String)
    name = sa.Column(sa.String)
    password = sa.Column(sa.String)
    role_id = sa.Column(sa.ForeignKey(Role.id))

    role = sa.orm.relationship(Role)


@pytest.fixture(scope='session')
def sa_engine():
    from sqlalchemy import create_engine
    return create_engine('sqlite:///:memory:', echo=True)


@pytest.fixture(scope='session')
def sa_session(sa_engine):
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker()
    Session.configure(bind=sa_engine)
    return Session()


@pytest.fixture(scope='session', autouse=True)
def migrate(sa_engine):
    Model.metadata.create_all(sa_engine)


def test_resource(app, api, client, sa_session):
    from flask_restler.sqlalchemy import ModelResource

    @api.connect
    class UserResouce(ModelResource):

        methods = 'get', 'post', 'put', 'delete'

        class Meta:
            model = User
            session = sa_session
            filters = 'login', 'name'
            schema_exclude = 'password',
            sorting = 'login',

    response = client.get('/api/v1/user')
    assert not response.json

    response = client.post_json('/api/v1/user', {
        'login': 'mike',
        'name': 'Mike Bacon',
    })
    assert 'password' not in response.json
    assert response.json

    response = client.put_json('/api/v1/user/1', {
        'name': 'Mike Summer',
    })
    assert response.json['name'] == 'Mike Summer'

    response = client.post_json('/api/v1/user', {
        'login': 'dave',
        'name': 'Dave Macaroff',
    })

    response = client.get('/api/v1/user')
    assert len(response.json) == 2

    response = client.get('/api/v1/user?sort=login,unknown')
    assert response.json[0]['login'] == 'dave'

    response = client.get('/api/v1/user?sort=-login')
    assert response.json[0]['login'] == 'mike'

    response = client.get('/api/v1/user?where={"login": "dave"}')
    assert len(response.json) == 1

    response = client.delete('/api/v1/user/1')
    assert not response.json

    response = client.get('/api/v1/user')
    assert len(response.json) == 1
