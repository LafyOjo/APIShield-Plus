import os
import json
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ["SKIP_MIGRATIONS"] = "1"

import app.core.db as db_module  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.crud.data_exports import upsert_export_config  # noqa: E402
from app.crud.tenants import create_tenant  # noqa: E402
from app.crud.users import create_user  # noqa: E402
from app.jobs.data_exports import run_data_exports  # noqa: E402
from app.models.data_exports import DataExportRun  # noqa: E402
from app.models.geo_event_aggs import GeoEventAgg  # noqa: E402
from app.models.incidents import Incident  # noqa: E402
from app.models.notification_channels import NotificationChannel  # noqa: E402
from app.models.notification_deliveries import NotificationDelivery  # noqa: E402
from app.models.notification_rules import NotificationRule  # noqa: E402
from app.models.revenue_impact import ConversionMetric  # noqa: E402
from app.models.security_events import SecurityEvent  # noqa: E402
from app.core.db import Base  # noqa: E402


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


def _seed_exports(db, *, tenant_id: int, now: datetime) -> None:
    incident = Incident(
        tenant_id=tenant_id,
        status="open",
        category="security",
        title="Login anomaly",
        severity="high",
        first_seen_at=now - timedelta(hours=2),
        last_seen_at=now - timedelta(hours=1),
    )
    db.add(incident)

    security_event = SecurityEvent(
        tenant_id=tenant_id,
        category="login",
        event_type="login_failure",
        severity="high",
        source="api",
        created_at=now - timedelta(hours=1),
    )
    db.add(security_event)

    geo_agg = GeoEventAgg(
        tenant_id=tenant_id,
        bucket_start=now.replace(minute=0, second=0, microsecond=0),
        event_category="login",
        count=5,
    )
    db.add(geo_agg)

    metric = ConversionMetric(
        tenant_id=tenant_id,
        metric_key="checkout",
        window_start=now - timedelta(hours=24),
        window_end=now,
        sessions=100,
        conversions=25,
        conversion_rate=0.25,
        captured_at=now - timedelta(hours=1),
    )
    db.add(metric)

    channel = NotificationChannel(
        tenant_id=tenant_id,
        type="slack",
        name="Ops",
        is_enabled=True,
    )
    db.add(channel)
    db.flush()

    rule = NotificationRule(
        tenant_id=tenant_id,
        name="Incidents",
        trigger_type="incident_opened",
        is_enabled=True,
    )
    db.add(rule)
    db.flush()

    delivery = NotificationDelivery(
        tenant_id=tenant_id,
        rule_id=rule.id,
        channel_id=channel.id,
        status="sent",
        created_at=now - timedelta(hours=1),
        sent_at=now - timedelta(minutes=30),
        dedupe_key=f"dedupe-{tenant_id}",
        payload_json={"message": "incident opened"},
    )
    db.add(delivery)
    db.commit()


def test_data_export_writes_partitioned_files(tmp_path):
    db_url = f"sqlite:///./data_export_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    settings.EXPORT_TARGET = "local"

    now = datetime.utcnow()
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Acme Export")
        tenant_id = tenant.id
        create_user(db, username="owner", password_hash=get_password_hash("pw"), role="user")
        _seed_exports(db, tenant_id=tenant_id, now=now)
        upsert_export_config(
            db,
            tenant_id,
            target_type="local",
            target_config=None,
            schedule="daily",
            datasets_enabled=["security_events"],
            format_value="jsonl.gz",
            is_enabled=True,
        )

    with SessionLocal() as db:
        run_data_exports(db, now=now, base_dir=tmp_path)

    date_bucket = now.strftime("%Y-%m-%d")
    dataset_dir = (
        tmp_path
        / "region=us"
        / f"tenant={tenant_id}"
        / "dataset=security_events"
    )
    partition_dir = dataset_dir / f"date={date_bucket}"
    assert dataset_dir.exists()
    assert partition_dir.exists()
    files = list(partition_dir.glob("*.jsonl.gz"))
    assert files, "Expected at least one export file"
    assert (dataset_dir / "schema.json").exists()


def test_data_export_run_records_status_and_metrics(tmp_path):
    db_url = f"sqlite:///./data_export_runs_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    settings.EXPORT_TARGET = "local"

    now = datetime.utcnow()
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Run Metrics")
        tenant_id = tenant.id
        _seed_exports(db, tenant_id=tenant_id, now=now)
        upsert_export_config(
            db,
            tenant_id,
            target_type="local",
            target_config=None,
            schedule="daily",
            datasets_enabled=["incidents"],
            format_value="jsonl.gz",
            is_enabled=True,
        )

    with SessionLocal() as db:
        run_data_exports(db, now=now, base_dir=tmp_path)
        run = db.query(DataExportRun).filter(DataExportRun.tenant_id == tenant_id).first()
        assert run is not None
        assert run.status == "success"
        assert run.files_written > 0
        assert run.bytes_written > 0


def test_data_export_scoped_to_tenant(tmp_path):
    db_url = f"sqlite:///./data_export_scope_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    settings.EXPORT_TARGET = "local"

    now = datetime.utcnow()
    with SessionLocal() as db:
        tenant_a = create_tenant(db, name="Tenant A")
        tenant_b = create_tenant(db, name="Tenant B")
        tenant_a_id = tenant_a.id
        tenant_b_id = tenant_b.id
        _seed_exports(db, tenant_id=tenant_a_id, now=now)
        _seed_exports(db, tenant_id=tenant_b_id, now=now)
        upsert_export_config(
            db,
            tenant_a_id,
            target_type="local",
            target_config=None,
            schedule="daily",
            datasets_enabled=["security_events"],
            format_value="jsonl.gz",
            is_enabled=True,
        )

    with SessionLocal() as db:
        run_data_exports(db, now=now, base_dir=tmp_path)

    date_bucket = now.strftime("%Y-%m-%d")
    partition_dir = (
        tmp_path
        / "region=us"
        / f"tenant={tenant_a_id}"
        / "dataset=security_events"
        / f"date={date_bucket}"
    )
    files = list(partition_dir.glob("*.jsonl.gz"))
    assert files
    import gzip

    with gzip.open(files[0], "rt", encoding="utf-8") as handle:
        lines = [json.loads(line) for line in handle if line.strip()]
    assert lines
    tenant_ids = {item.get("tenant_id") for item in lines}
    assert tenant_ids == {tenant_a_id}


def test_exports_include_region_partitioning(tmp_path):
    db_url = f"sqlite:///./data_export_region_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    settings.EXPORT_TARGET = "local"

    now = datetime.utcnow()
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Region Tenant")
        tenant_id = tenant.id
        _seed_exports(db, tenant_id=tenant_id, now=now)
        upsert_export_config(
            db,
            tenant_id,
            target_type="local",
            target_config=None,
            schedule="daily",
            datasets_enabled=["security_events"],
            format_value="jsonl.gz",
            is_enabled=True,
        )

    with SessionLocal() as db:
        run_data_exports(db, now=now, base_dir=tmp_path)

    date_bucket = now.strftime("%Y-%m-%d")
    partition_dir = (
        tmp_path
        / "region=us"
        / f"tenant={tenant_id}"
        / "dataset=security_events"
        / f"date={date_bucket}"
    )
    assert partition_dir.exists()
