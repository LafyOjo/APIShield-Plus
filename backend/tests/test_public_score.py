import base64
import os
from datetime import datetime, timedelta
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

private_key = Ed25519PrivateKey.generate()
private_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
public_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

os.environ["TRUST_SCORE_SIGNING_PRIVATE_KEY"] = base64.urlsafe_b64encode(private_bytes).decode("utf-8").rstrip("=")
os.environ["TRUST_SCORE_SIGNING_PUBLIC_KEY"] = base64.urlsafe_b64encode(public_bytes).decode("utf-8").rstrip("=")
os.environ["TRUST_SCORE_SIGNING_KEY_ID"] = "test-key-1"
os.environ.setdefault("DATABASE_URL", "sqlite:///./public_score_test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.main import app  # noqa: E402
import app.core.db as db_module  # noqa: E402
import app.core.access_log as access_log_module  # noqa: E402
import app.core.policy as policy_module  # noqa: E402
from app.core.db import Base  # noqa: E402
from app.core.config import settings as app_settings  # noqa: E402
from app.core.score_signing import load_public_key, verify_signature  # noqa: E402
from app.crud.tenants import create_tenant  # noqa: E402
from app.models.trust_scoring import TrustSnapshot  # noqa: E402
from app.models.websites import Website  # noqa: E402
from app.models.website_environments import WebsiteEnvironment  # noqa: E402


client = TestClient(app)

app_settings.TRUST_SCORE_SIGNING_PRIVATE_KEY = os.environ["TRUST_SCORE_SIGNING_PRIVATE_KEY"]
app_settings.TRUST_SCORE_SIGNING_PUBLIC_KEY = os.environ["TRUST_SCORE_SIGNING_PUBLIC_KEY"]
app_settings.TRUST_SCORE_SIGNING_KEY_ID = os.environ["TRUST_SCORE_SIGNING_KEY_ID"]


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


def test_public_score_endpoint_returns_signed_proof():
    db_url = f"sqlite:///./public_score_{uuid4().hex}.db"
    SessionLocal = _setup_db(db_url)
    with SessionLocal() as db:
        tenant = create_tenant(db, name="Score Tenant")
        website = Website(tenant_id=tenant.id, domain="score.example.com")
        db.add(website)
        db.commit()
        db.refresh(website)
        env = WebsiteEnvironment(website_id=website.id, name="production")
        db.add(env)
        db.commit()
        db.refresh(env)
        snapshot = TrustSnapshot(
            tenant_id=tenant.id,
            website_id=website.id,
            environment_id=env.id,
            bucket_start=datetime.utcnow() - timedelta(minutes=5),
            path=None,
            trust_score=91,
            confidence=0.82,
            factor_count=2,
        )
        db.add(snapshot)
        db.commit()
        website_id = website.id

    resp = client.get(f"/public/score/v1?website_id={website_id}")
    assert resp.status_code == 200
    signature = resp.headers.get("X-Proof-Signature")
    assert signature
    assert resp.headers.get("etag")
    payload = resp.json()
    public_key = load_public_key(os.environ["TRUST_SCORE_SIGNING_PUBLIC_KEY"])
    assert verify_signature(payload, signature, public_key) is True

    tampered = dict(payload)
    tampered["trust_score_current"] = 12
    assert verify_signature(tampered, signature, public_key) is False
