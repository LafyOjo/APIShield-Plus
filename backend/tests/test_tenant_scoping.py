import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.db import Base
from app.crud.tenants import create_tenant
from app.crud.websites import create_website
from app.models.websites import Website
from app.tenancy.errors import TenantNotFound
from app.tenancy.scoping import get_tenant_owned_or_404, scoped_query


@pytest.fixture
def db_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/tenant_scoping.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def test_scoped_query_raises_if_model_missing_tenant_id():
    class Dummy:
        pass

    class FakeSession:
        def query(self, model):
            return self

        def filter(self, *_args, **_kwargs):
            return self

    with pytest.raises(ValueError):
        scoped_query(FakeSession(), Dummy, tenant_id=1)


def test_get_tenant_owned_or_404_returns_only_owned_resource(db_session):
    tenant = create_tenant(db_session, name="Acme")
    website = create_website(db_session, tenant.id, "acme.com")
    owned = get_tenant_owned_or_404(db_session, Website, tenant.id, website.id)
    assert owned.id == website.id


def test_get_tenant_owned_or_404_blocks_cross_tenant(db_session):
    tenant_a = create_tenant(db_session, name="Umbrella")
    tenant_b = create_tenant(db_session, name="Wayne")
    website_b = create_website(db_session, tenant_b.id, "wayne.com")
    with pytest.raises(TenantNotFound):
        get_tenant_owned_or_404(db_session, Website, tenant_a.id, website_b.id)
