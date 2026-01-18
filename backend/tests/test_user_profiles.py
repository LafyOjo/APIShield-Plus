import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")

from app.main import app
import app.core.db as db_module
import app.core.access_log as access_log_module
import app.core.policy as policy_module
from app.core.db import Base
from app.core.security import get_password_hash
from app.crud.users import create_user
from app.models.user_profiles import UserProfile


client = TestClient(app)


def _setup_db(db_url: str):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db_module.engine = engine
    db_module.SessionLocal = SessionLocal
    access_log_module.SessionLocal = SessionLocal
    policy_module.SessionLocal = SessionLocal
    access_log_module.create_access_log = lambda db, username, path: None
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def _login(username: str) -> str:
    resp = client.post("/login", json={"username": username, "password": "pw"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_profile_created_on_first_fetch():
    db_url = f"sqlite:///./profile_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        user = create_user(db, username="alice", password_hash=get_password_hash("pw"), role="user")
        user_id = user.id

    token = _login("alice")
    resp = client.get(
        "/api/v1/profile",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["display_name"] == "alice"

    with SessionLocal() as db:
        profile = (
            db.query(UserProfile)
            .filter(UserProfile.user_id == user_id)
            .first()
        )
        assert profile is not None
        assert profile.display_name == "alice"


def test_update_profile_persists_changes():
    db_url = f"sqlite:///./profile_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        create_user(db, username="bob", password_hash=get_password_hash("pw"), role="user")

    token = _login("bob")
    resp = client.patch(
        "/api/v1/profile",
        json={"display_name": "Bobby", "timezone": "UTC"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["display_name"] == "Bobby"
    assert payload["timezone"] == "UTC"

    with SessionLocal() as db:
        profile = (
            db.query(UserProfile)
            .filter(UserProfile.display_name == "Bobby")
            .first()
        )
        assert profile is not None
