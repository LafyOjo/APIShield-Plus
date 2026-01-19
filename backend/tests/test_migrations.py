import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def _make_alembic_config(db_url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    alembic_ini = backend_dir / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", db_url)
    config.set_main_option("prepend_sys_path", str(backend_dir))
    return config


def _table_names(db_url: str) -> set[str]:
    engine = create_engine(db_url, future=True)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    engine.dispose()
    return tables


def test_migration_upgrade_downgrade_cycle(tmp_path):
    db_path = tmp_path / "migration_test.db"
    db_url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SECRET_KEY"] = "secret"

    config = _make_alembic_config(db_url)

    command.upgrade(config, "head")
    tables = _table_names(db_url)
    expected = {
        "tenants",
        "plans",
        "subscriptions",
        "memberships",
        "websites",
        "website_environments",
        "api_keys",
        "tenant_settings",
        "tenant_usage",
        "data_retention_policies",
        "feature_entitlements",
        "domain_verifications",
        "external_integrations",
        "project_tags",
        "website_tags",
        "user_profiles",
        "invites",
        "behaviour_events",
        "behaviour_sessions",
        "anomaly_signal_events",
        "ip_enrichments",
        "geo_event_aggs",
    }
    assert expected.issubset(tables)

    command.downgrade(config, "base")
    tables = _table_names(db_url)
    assert "tenants" not in tables

    command.upgrade(config, "head")
    tables = _table_names(db_url)
    assert expected.issubset(tables)
