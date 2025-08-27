import os

os.environ['DATABASE_URL'] = 'sqlite:///./test.db'
os.environ['SECRET_KEY'] = 'test-secret'

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.crud.users import create_user  # noqa: E402
from app.crud.policies import create_policy  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402

client = TestClient(app)


def setup_function(_):
    with SessionLocal() as db:
        strict = create_policy(db, failed_attempts_limit=1)
        lenient = create_policy(db, failed_attempts_limit=3)
        create_user(
            db,
            username='ben',
            password_hash=get_password_hash('pw'),
            policy_id=strict.id,
        )
        create_user(
            db,
            username='alice',
            password_hash=get_password_hash('pw'),
            policy_id=lenient.id,
        )


def test_policy_enforcement():
    # Ben has strict policy: second failure should block
    resp = client.post('/login', json={'username': 'ben', 'password': 'wrong'})
    assert resp.status_code == 401
    resp = client.post('/login', json={'username': 'ben', 'password': 'wrong'})
    assert resp.status_code == 429

    # Alice has lenient policy: two failures allowed, third blocked
    resp = client.post('/login', json={'username': 'alice', 'password': 'wrong'})
    assert resp.status_code == 401
    resp = client.post('/login', json={'username': 'alice', 'password': 'wrong'})
    assert resp.status_code == 401
    resp = client.post('/login', json={'username': 'alice', 'password': 'wrong'})
    assert resp.status_code == 401
    resp = client.post('/login', json={'username': 'alice', 'password': 'wrong'})
    assert resp.status_code == 429
