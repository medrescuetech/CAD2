import typing as t
from flask.testing import FlaskClient


def login(client: FlaskClient, username: str, password: str) -> int:
    r_get = client.get('/auth/login')
    r_post = client.post('/auth/login', data={'username': username, 'password': password}, follow_redirects=False)
    return r_post.status_code


def get(client: FlaskClient, path: str) -> int:
    r = client.get(path)
    return r.status_code
