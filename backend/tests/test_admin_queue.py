import os
from datetime import timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ["SKIP_MIGRATIONS"] = "1"

from app.main import app  # noqa: E402
import app.core.db as db_module  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.core.queue import clear_job_handlers, enqueue_job, register_job_handler  # noqa: E402
from app.core.time import utcnow  # noqa: E402
from app.jobs.queue_worker import run_queue_once  # noqa: E402
from app.crud.users import create_user  # noqa: E402
from app.core.db import Base  # noqa: E402
from app.models.job_dead_letters import JobDeadLetter  # noqa: E402


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
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def _login(username: str) -> str:
    resp = client.post("/login", json={"username": username, "password": "pw"})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_dead_letter_list_requires_platform_admin():
    db_url = f"sqlite:///./queue_admin_block_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        create_user(db, username="user", password_hash=get_password_hash("pw"), role="user")

    token = _login("user")
    resp = client.get(
        "/api/v1/admin/queue/dead-letters",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_admin_can_view_dead_letters():
    db_url = f"sqlite:///./queue_admin_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    clear_job_handlers()

    def _fail(_db, _payload):
        raise RuntimeError("boom")

    register_job_handler("explode", _fail)

    with SessionLocal() as db:
        create_user(
            db,
            username="admin",
            password_hash=get_password_hash("pw"),
            role="user",
            is_platform_admin=True,
        )
        enqueue_job(
            db,
            job_type="explode",
            queue_name="bulk",
            max_attempts=1,
            payload={"value": 1},
        )

    with SessionLocal() as db:
        run_queue_once(db, queue_name="bulk", worker_id="worker-queue", limit=5)

    with SessionLocal() as db:
        dead_letters = db.query(JobDeadLetter).all()
        assert dead_letters
        dead_letters[0].failed_at = dead_letters[0].failed_at - timedelta(seconds=1)
        db.commit()

    token = _login("admin")
    resp = client.get(
        "/api/v1/admin/queue/dead-letters",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload
    assert payload[0]["job_type"] == "explode"
