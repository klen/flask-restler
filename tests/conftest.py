import pytest
from flask.testing import FlaskClient
import json


class TestClient(FlaskClient):

    def __init__(self, *args, **kwargs):
        self.headers = {}
        super(TestClient, self).__init__(*args, **kwargs)

    def add_header(self, name, value):
        self.headers[name] = value

    def open(self, *args, **kwargs):
        if self.headers:
            headers = dict(kwargs.get('headers', {}))
            headers.update(self.headers)
            kwargs['headers'] = headers
        return super(TestClient, self).open(*args, **kwargs)

    def get_json(self, url, **kwargs):
        kwargs['content_type'] = 'application/json'
        return self.get(url, **kwargs)

    def post_json(self, url, data=None, **kwargs):
        data = json.dumps(data)
        kwargs['content_type'] = 'application/json'
        return self.post(url, data=data, **kwargs)

    def put_json(self, url, data=None, **kwargs):
        data = json.dumps(data)
        kwargs['content_type'] = 'application/json'
        return self.put(url, data=data, **kwargs)


@pytest.fixture(scope='function')
def app():
    """Create test's application."""
    from flask import Flask

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.test_client_class = TestClient

    @app.route('/')
    def index():
        return 'OK'

    return app


@pytest.fixture(scope='function')
def api(app):
    from flask_restler import Api

    api = Api('REST API', __name__, url_prefix="/api/v1")
    api.register(app)
    return api


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
