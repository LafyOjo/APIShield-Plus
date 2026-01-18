import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.db import Base
from app.core.entitlements import resolve_entitlements
from app.crud.plans import list_active_plans
from app.models.plans import Plan
from app.seed.utils import seed_default_plans


@pytest.fixture
def db_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/plans_test.db"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SKIP_MIGRATIONS"] = "1"
    engine = create_engine(db_url, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    with TestingSessionLocal() as session:
        yield session


def test_seed_plans_is_idempotent(db_session):
    seed_default_plans(db_session)
    seed_default_plans(db_session)
    count = db_session.query(Plan).count()
    assert count == 4


def test_list_active_plans_returns_expected(db_session):
    seed_default_plans(db_session)
    inactive = Plan(
        name="Legacy",
        price_monthly=19,
        limits_json={"websites": 1},
        features_json={"heatmaps": False},
        is_active=False,
    )
    db_session.add(inactive)
    db_session.commit()

    active = list_active_plans(db_session)
    names = {plan.name for plan in active}
    assert "Legacy" not in names
    assert {"Free", "Starter", "Pro", "Business"} <= names


def test_entitlements_resolution_returns_limits_and_features(db_session):
    plan = Plan(
        name="Test",
        price_monthly=0,
        limits_json={"websites": 2},
        features_json={"heatmaps": True},
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)

    entitlements = resolve_entitlements(plan)
    assert entitlements["limits"]["websites"] == 2
    assert entitlements["features"]["heatmaps"] is True
