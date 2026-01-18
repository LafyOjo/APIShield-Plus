import importlib

import pytest
from pydantic import ValidationError


def _load_settings(monkeypatch, extra_env=None):
    import app.core.config as config

    # Ensure required keys exist for import.
    monkeypatch.setenv("SKIP_MIGRATIONS", "1")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SECRET_KEY", "secret")
    if extra_env:
        for key, value in extra_env.items():
            monkeypatch.setenv(key, value)
    importlib.reload(config)
    return config.Settings


def test_settings_defaults(monkeypatch):
    Settings = _load_settings(monkeypatch)
    cfg = Settings(_env_file=None)
    assert cfg.TENANT_HEADER_NAME == "X-Tenant-ID"
    assert cfg.REQUIRE_TENANT_HEADER is True
    assert cfg.DEFAULT_TENANT_SLUG is None
    assert cfg.ALLOW_MULTI_TENANT_DEV_BYPASS is False
    assert cfg.TENANT_STRICT_404 is True
    assert cfg.TENANT_CONTEXT_RESOLUTION_ORDER == ["header", "jwt", "default"]
    assert cfg.INVITE_TOKEN_TTL_HOURS == 72
    assert cfg.AUDIT_WS_REQUIRE_TENANT is True


def test_settings_env_overrides(monkeypatch):
    Settings = _load_settings(
        monkeypatch,
        {
            "DATABASE_URL": "sqlite:///:memory:",
            "SECRET_KEY": "override",
            "TENANT_HEADER_NAME": "X-Org",
            "REQUIRE_TENANT_HEADER": "false",
            "DEFAULT_TENANT_SLUG": "dev-tenant",
            "ALLOW_MULTI_TENANT_DEV_BYPASS": "true",
            "TENANT_STRICT_404": "false",
            "TENANT_CONTEXT_RESOLUTION_ORDER": '["jwt","header"]',
            "INVITE_TOKEN_TTL_HOURS": "24",
            "AUDIT_WS_REQUIRE_TENANT": "false",
        },
    )
    cfg = Settings(_env_file=None)
    assert cfg.TENANT_HEADER_NAME == "X-Org"
    assert cfg.REQUIRE_TENANT_HEADER is False
    assert cfg.DEFAULT_TENANT_SLUG == "dev-tenant"
    assert cfg.ALLOW_MULTI_TENANT_DEV_BYPASS is True
    assert cfg.TENANT_STRICT_404 is False
    assert cfg.TENANT_CONTEXT_RESOLUTION_ORDER == ["jwt", "header"]
    assert cfg.INVITE_TOKEN_TTL_HOURS == 24
    assert cfg.AUDIT_WS_REQUIRE_TENANT is False
    assert cfg.DATABASE_URL == "sqlite:///:memory:"
    assert cfg.SECRET_KEY == "override"


def test_invite_ttl_must_be_positive(monkeypatch):
    Settings = _load_settings(monkeypatch)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, INVITE_TOKEN_TTL_HOURS=0)
