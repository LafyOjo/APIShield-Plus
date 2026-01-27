import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.db import Base
from app.crud.tenants import create_tenant
from app.crud.websites import create_website
from app.crud.website_stack_profiles import apply_stack_detection, set_stack_manual_override


def _make_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/stack_profiles.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def test_stack_profile_created_from_agent_hints(tmp_path):
    session = _make_session(tmp_path)
    tenant = create_tenant(session, name="Acme")
    website = create_website(session, tenant.id, "acme.com")

    profile = apply_stack_detection(
        session,
        tenant_id=tenant.id,
        website_id=website.id,
        hints={"nextjs_detected": True},
    )

    assert profile.stack_type == "nextjs"
    assert profile.confidence >= 0.5
    assert profile.manual_override is False

    session.close()


def test_stack_profile_manual_override_persists(tmp_path):
    session = _make_session(tmp_path)
    tenant = create_tenant(session, name="Umbrella")
    website = create_website(session, tenant.id, "umbrella.com")

    apply_stack_detection(
        session,
        tenant_id=tenant.id,
        website_id=website.id,
        hints={"shopify_detected": True},
    )

    overridden = set_stack_manual_override(
        session,
        tenant_id=tenant.id,
        website_id=website.id,
        stack_type="wordpress",
    )
    assert overridden.manual_override is True
    assert overridden.stack_type == "wordpress"

    updated = apply_stack_detection(
        session,
        tenant_id=tenant.id,
        website_id=website.id,
        hints={"nextjs_detected": True},
    )
    assert updated.stack_type == "wordpress"
    assert updated.manual_override is True

    session.close()
