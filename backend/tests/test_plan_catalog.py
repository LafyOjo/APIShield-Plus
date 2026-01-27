import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.billing.catalog import get_plan_tiers
from app.core.db import Base
from app.core.entitlements import ALLOWED_FEATURES
from app.models.plans import Plan
from app.seed.utils import seed_default_plans


@pytest.fixture
def db_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/plan_catalog.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def test_plan_catalog_matches_entitlements_resolver(db_session):
    tiers = get_plan_tiers()
    assert tiers

    for key, tier in tiers.items():
        features = tier.get("features") or {}
        assert set(features.keys()).issubset(ALLOWED_FEATURES)
        assert tier.get("limits") is not None
        assert tier.get("plan_name")

    seed_default_plans(db_session)
    plans_by_name = {plan.name: plan for plan in db_session.query(Plan).all()}

    for tier in tiers.values():
        name = tier["plan_name"]
        plan = plans_by_name.get(name)
        assert plan is not None
        assert plan.limits_json == tier["limits"]
        for feature, enabled in tier["features"].items():
            assert plan.features_json.get(feature) == enabled
