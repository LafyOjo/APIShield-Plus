import os

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.db import Base
from app.core.security import get_password_hash
from app.crud.project_tags import attach_tag_to_website, create_tag
from app.crud.tenants import create_tenant
from app.crud.users import create_user
from app.crud.websites import create_website
from app.models.project_tags import WebsiteTag


@pytest.fixture
def db_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/fk_test.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def test_delete_user_sets_created_by_to_null(db_session):
    user = create_user(db_session, username="creator", password_hash=get_password_hash("pw"))
    tenant = create_tenant(db_session, name="Acme", created_by_user_id=user.id)
    website = create_website(db_session, tenant.id, "acme.com", created_by_user_id=user.id)

    db_session.delete(user)
    db_session.commit()

    db_session.refresh(tenant)
    db_session.refresh(website)
    assert tenant.created_by_user_id is None
    assert website.created_by_user_id is None


def test_hard_delete_tenant_is_restricted(db_session):
    tenant = create_tenant(db_session, name="Acme")
    create_website(db_session, tenant.id, "restrict.com")

    db_session.delete(tenant)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_join_table_cascades_on_parent_delete(db_session):
    tenant = create_tenant(db_session, name="Acme")
    website = create_website(db_session, tenant.id, "tags.com")
    tag = create_tag(db_session, tenant.id, "Checkout")
    attach_tag_to_website(db_session, tenant.id, website.id, tag.id)

    db_session.delete(tag)
    db_session.commit()

    remaining = (
        db_session.query(WebsiteTag)
        .filter(WebsiteTag.website_id == website.id, WebsiteTag.tag_id == tag.id)
        .first()
    )
    assert remaining is None
