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
        "tenant_retention_policies",
        "feature_entitlements",
        "domain_verifications",
        "external_integrations",
        "status_components",
        "status_incidents",
        "trust_snapshots",
        "trust_factor_aggs",
        "trust_badge_configs",
        "integration_listings",
        "integration_install_events",
        "marketplace_templates",
        "template_import_events",
        "growth_snapshots",
        "revenue_leak_estimates",
        "website_stack_profiles",
        "remediation_playbooks",
        "protection_presets",
        "verification_check_runs",
        "onboarding_states",
        "user_tour_states",
        "activation_metrics",
        "email_queue",
        "referral_program_config",
        "referral_invites",
        "referral_redemptions",
        "credit_ledger",
        "affiliate_partners",
        "affiliate_attributions",
        "affiliate_commission_ledger",
        "partner_users",
        "partner_leads",
        "feature_flags",
        "experiments",
        "experiment_assignments",
        "notification_channels",
        "notification_rules",
        "notification_rule_channels",
        "notification_deliveries",
        "backfill_runs",
        "project_tags",
        "website_tags",
        "user_profiles",
        "invites",
        "behaviour_events",
        "behaviour_sessions",
        "anomaly_signal_events",
        "security_events",
        "conversion_metrics",
        "baseline_models",
        "impact_estimates",
        "incidents",
        "incident_security_event_links",
        "incident_anomaly_signal_links",
        "incident_recoveries",
        "prescription_bundles",
        "prescription_items",
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


def test_migrations_apply_clean_db(tmp_path):
    db_path = tmp_path / "migration_clean.db"
    db_url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SECRET_KEY"] = "secret"

    config = _make_alembic_config(db_url)

    command.upgrade(config, "head")
    tables = _table_names(db_url)
    assert "alembic_version" in tables

    command.downgrade(config, "base")
