import os
from datetime import timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ["SKIP_MIGRATIONS"] = "1"

from app.core import config as config_module
from app.core.db import Base
from app.core.queue import clear_job_handlers, enqueue_job, register_job_handler
from app.core.rate_limit import reset_state
from app.core.time import utcnow
from app.jobs.queue_worker import run_queue_group_once, run_queue_once
from app.models.job_dead_letters import JobDeadLetter
from app.models.job_queue import JobQueue


def _setup_db(db_url: str):
    reset_state()
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def _naive(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def test_critical_queue_jobs_processed_before_bulk_queue():
    db_url = f"sqlite:///./queue_order_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    processed: list[str] = []

    clear_job_handlers()

    def _handler(_db, payload):
        processed.append(payload["label"])

    register_job_handler("test_job", _handler)

    with SessionLocal() as db:
        enqueue_job(
            db,
            job_type="test_job",
            queue_name="bulk",
            payload={"label": "bulk"},
        )
        enqueue_job(
            db,
            job_type="test_job",
            queue_name="critical",
            payload={"label": "critical"},
        )

    with SessionLocal() as db:
        run_queue_group_once(
            db,
            queue_names=["critical", "bulk"],
            worker_id="worker-a",
            limit=10,
        )

    assert processed == ["critical", "bulk"]


def test_tenant_fairness_throttles_excessive_background_jobs(monkeypatch):
    db_url = f"sqlite:///./queue_fairness_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    processed: list[int] = []

    clear_job_handlers()
    register_job_handler("work", lambda _db, payload: processed.append(payload["tenant_id"]))

    monkeypatch.setattr(config_module.settings, "QUEUE_TENANT_RPM_STANDARD", 1)
    monkeypatch.setattr(config_module.settings, "QUEUE_TENANT_BURST_STANDARD", 1)
    monkeypatch.setattr(config_module.settings, "QUEUE_TENANT_MAX_IN_FLIGHT_STANDARD", 5)

    with SessionLocal() as db:
        enqueue_job(db, job_type="work", queue_name="standard", tenant_id=1, payload={"tenant_id": 1})
        enqueue_job(db, job_type="work", queue_name="standard", tenant_id=1, payload={"tenant_id": 1})
        enqueue_job(db, job_type="work", queue_name="standard", tenant_id=2, payload={"tenant_id": 2})

    with SessionLocal() as db:
        run_queue_once(db, queue_name="standard", worker_id="worker-b", limit=5)
        deferred = (
            db.query(JobQueue)
            .filter(JobQueue.queue_name == "standard", JobQueue.status == "queued")
            .all()
        )

    assert processed.count(1) == 1
    assert processed.count(2) == 1
    assert deferred
    assert _naive(deferred[0].run_at) > _naive(utcnow())


def test_dead_letter_records_failed_jobs_after_max_retries():
    db_url = f"sqlite:///./queue_dead_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)

    clear_job_handlers()

    def _fail(_db, _payload):
        raise RuntimeError("boom")

    register_job_handler("explode", _fail)

    with SessionLocal() as db:
        enqueue_job(
            db,
            job_type="explode",
            queue_name="standard",
            max_attempts=2,
            payload={"value": 1},
        )

    with SessionLocal() as db:
        run_queue_once(db, queue_name="standard", worker_id="worker-c", limit=5)
        job = db.query(JobQueue).first()
        assert job is not None
        job.run_at = _naive(utcnow()) - timedelta(seconds=1)
        db.commit()

    with SessionLocal() as db:
        run_queue_once(db, queue_name="standard", worker_id="worker-c", limit=5)
        remaining = db.query(JobQueue).count()
        dead_letters = db.query(JobDeadLetter).all()

    assert remaining == 0
    assert len(dead_letters) == 1
    assert dead_letters[0].last_error is not None
