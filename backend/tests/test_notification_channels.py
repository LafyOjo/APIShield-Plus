import os
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("INTEGRATION_ENCRYPTION_KEY", "a" * 32)
os.environ["SKIP_MIGRATIONS"] = "1"

from app.core.crypto import decrypt_json
from app.core.db import Base
from app.crud.notification_channels import create_channel, get_channel
from app.crud.tenants import create_tenant
from app.schemas.notification_channels import NotificationChannelRead


def _setup_db(db_url: str):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return SessionLocal


def test_notification_channel_secrets_are_encrypted_at_rest():
    db_url = f"sqlite:///./notification_channels_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Acme")
        secret = {"webhook_url": "https://hooks.slack.com/services/T000/B000/SECRET"}
        channel = create_channel(
            db,
            tenant_id=tenant.id,
            channel_type="slack",
            name="Ops Slack",
            config_public={"channel": "#ops"},
            config_secret=secret,
        )
        assert channel.config_secret_enc is not None
        assert "hooks.slack.com" not in channel.config_secret_enc
        decrypted = decrypt_json(channel.config_secret_enc)
        assert decrypted == secret


def test_notification_channel_read_does_not_expose_secrets():
    db_url = f"sqlite:///./notification_channels_read_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Umbrella")
        channel = create_channel(
            db,
            tenant_id=tenant.id,
            channel_type="webhook",
            name="Security Webhook",
            config_public={"domain": "hooks.example.com"},
            config_secret={"url": "https://hooks.example.com/secret"},
        )
        payload = NotificationChannelRead.from_orm(channel).dict()
        assert "config_secret_enc" not in payload
        assert "config_secret" not in payload
        assert payload["is_configured"] is True


def test_notification_channel_tenant_scoped():
    db_url = f"sqlite:///./notification_channels_scope_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant_a = create_tenant(db, name="Wayne")
        tenant_b = create_tenant(db, name="Stark")
        channel = create_channel(
            db,
            tenant_id=tenant_a.id,
            channel_type="email",
            name="Security Email",
            config_public={"recipients": ["sec@example.com"]},
        )
        assert get_channel(db, tenant_b.id, channel.id) is None
