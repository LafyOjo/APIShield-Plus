import importlib
import os

import pytest
from pydantic import ValidationError

os.environ["SKIP_MIGRATIONS"] = "1"


def _load_settings(monkeypatch, extra_env=None):
    for key in (
        "ENVIRONMENT",
        "TENANT_HEADER_NAME",
        "REQUIRE_TENANT_HEADER",
        "DEFAULT_TENANT_SLUG",
        "ALLOW_MULTI_TENANT_DEV_BYPASS",
        "TENANT_STRICT_404",
        "TENANT_CONTEXT_RESOLUTION_ORDER",
        "INVITE_TOKEN_TTL_HOURS",
        "INVITE_TOKEN_RETURN_IN_RESPONSE",
        "AUDIT_WS_REQUIRE_TENANT",
        "API_KEY_SECRET_RETURN_IN_RESPONSE",
        "AGENT_URL",
        "TRUST_PROXY_HEADERS",
        "TRUSTED_PROXY_IPS",
        "TRUSTED_IP_HEADERS",
        "ALLOW_RAW_IP_SECURITY_ENDPOINTS",
        "SECURITY_HEADERS_ENABLED",
        "HSTS_MAX_AGE",
        "HSTS_INCLUDE_SUBDOMAINS",
        "HSTS_PRELOAD",
        "X_FRAME_OPTIONS",
        "REFERRER_POLICY",
        "CSP_DEFAULT",
        "INGEST_DEFAULT_RPM",
        "INGEST_DEFAULT_BURST",
        "INGEST_IP_RPM",
        "INGEST_IP_BURST",
        "INGEST_MAX_BODY_BYTES",
        "INGEST_INVALID_BAN_THRESHOLD",
        "INGEST_INVALID_WINDOW_SECONDS",
        "INGEST_BAN_SECONDS",
        "INGEST_SECURITY_DEFAULT_RPM",
        "INGEST_SECURITY_DEFAULT_BURST",
        "INGEST_SECURITY_IP_RPM",
        "INGEST_SECURITY_IP_BURST",
        "INGEST_ABUSE_BAN_THRESHOLD",
        "INGEST_ABUSE_WINDOW_SECONDS",
        "INGEST_ABUSE_BAN_SECONDS",
        "GEO_PROVIDER",
        "GEO_DB_PATH",
        "GEO_ASN_DB_PATH",
        "GEO_API_KEY",
        "GEO_API_BASE_URL",
        "GEO_ENRICHMENT_TTL_DAYS",
        "ZERO_TRUST_API_KEY",
        "FRONTEND_BASE_URL",
        "SSO_STATE_TTL_SECONDS",
        "SSO_DISCOVERY_TIMEOUT_SECONDS",
        "SSO_TOKEN_TIMEOUT_SECONDS",
        "SSO_DISCOVERY_CACHE_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)

    # Ensure required keys exist for import.
    monkeypatch.setenv("SKIP_MIGRATIONS", "1")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("SECRET_KEY", "secret")
    if extra_env:
        for key, value in extra_env.items():
            monkeypatch.setenv(key, value)
    import app.core.config as config
    importlib.reload(config)
    return config.Settings


def test_settings_defaults(monkeypatch):
    Settings = _load_settings(monkeypatch)
    cfg = Settings(_env_file=None)
    assert cfg.ENVIRONMENT == "development"
    assert cfg.TENANT_HEADER_NAME == "X-Tenant-ID"
    assert cfg.REQUIRE_TENANT_HEADER is True
    assert cfg.DEFAULT_TENANT_SLUG is None
    assert cfg.ALLOW_MULTI_TENANT_DEV_BYPASS is False
    assert cfg.TENANT_STRICT_404 is True
    assert cfg.TENANT_CONTEXT_RESOLUTION_ORDER == ["header", "jwt", "default"]
    assert cfg.INVITE_TOKEN_TTL_HOURS == 72
    assert cfg.INVITE_TOKEN_RETURN_IN_RESPONSE is False
    assert cfg.AUDIT_WS_REQUIRE_TENANT is True
    assert cfg.API_KEY_SECRET_RETURN_IN_RESPONSE is False
    assert cfg.AGENT_URL == "https://cdn.yourapp.com/agent.js"
    assert cfg.TRUST_PROXY_HEADERS is False
    assert cfg.TRUSTED_PROXY_IPS == []
    assert cfg.TRUSTED_IP_HEADERS == [
        "CF-Connecting-IP",
        "X-Forwarded-For",
        "X-Real-IP",
    ]
    assert cfg.ALLOW_RAW_IP_SECURITY_ENDPOINTS is False
    assert cfg.SECURITY_HEADERS_ENABLED is True
    assert cfg.HSTS_MAX_AGE == 31536000
    assert cfg.HSTS_INCLUDE_SUBDOMAINS is True
    assert cfg.HSTS_PRELOAD is False
    assert cfg.X_FRAME_OPTIONS == "DENY"
    assert cfg.REFERRER_POLICY == "strict-origin-when-cross-origin"
    assert "default-src" in cfg.CSP_DEFAULT
    assert cfg.INGEST_DEFAULT_RPM == 120
    assert cfg.INGEST_DEFAULT_BURST == 120
    assert cfg.INGEST_IP_RPM == 300
    assert cfg.INGEST_IP_BURST == 300
    assert cfg.INGEST_MAX_BODY_BYTES == 65536
    assert cfg.INGEST_INVALID_BAN_THRESHOLD == 20
    assert cfg.INGEST_INVALID_WINDOW_SECONDS == 60
    assert cfg.INGEST_BAN_SECONDS == 600
    assert cfg.INGEST_SECURITY_DEFAULT_RPM == 60
    assert cfg.INGEST_SECURITY_DEFAULT_BURST == 60
    assert cfg.INGEST_SECURITY_IP_RPM == 120
    assert cfg.INGEST_SECURITY_IP_BURST == 120
    assert cfg.INGEST_SECURITY_DEFAULT_RPM < cfg.INGEST_DEFAULT_RPM
    assert cfg.INGEST_ABUSE_BAN_THRESHOLD == 10
    assert cfg.INGEST_ABUSE_WINDOW_SECONDS == 60
    assert cfg.INGEST_ABUSE_BAN_SECONDS == 900
    assert cfg.GEO_PROVIDER == "local"
    assert cfg.GEO_DB_PATH == "/data/geo/GeoLite2-City.mmdb"
    assert cfg.GEO_ASN_DB_PATH == "/data/geo/GeoLite2-ASN.mmdb"
    assert cfg.GEO_API_KEY is None
    assert cfg.GEO_API_BASE_URL is None
    assert cfg.GEO_ENRICHMENT_TTL_DAYS == 30
    assert cfg.ZERO_TRUST_API_KEY is None
    assert cfg.FRONTEND_BASE_URL == "http://localhost:3000"
    assert cfg.SSO_STATE_TTL_SECONDS == 600
    assert cfg.SSO_DISCOVERY_TIMEOUT_SECONDS == 5
    assert cfg.SSO_TOKEN_TIMEOUT_SECONDS == 5
    assert cfg.SSO_DISCOVERY_CACHE_SECONDS == 300


def test_settings_env_overrides(monkeypatch):
    Settings = _load_settings(
        monkeypatch,
        {
            "DATABASE_URL": "sqlite:///:memory:",
            "SECRET_KEY": "override",
            "ENVIRONMENT": "production",
            "TENANT_HEADER_NAME": "X-Org",
            "REQUIRE_TENANT_HEADER": "false",
            "DEFAULT_TENANT_SLUG": "dev-tenant",
            "ALLOW_MULTI_TENANT_DEV_BYPASS": "true",
            "TENANT_STRICT_404": "false",
            "TENANT_CONTEXT_RESOLUTION_ORDER": '["jwt","header"]',
            "INVITE_TOKEN_TTL_HOURS": "24",
            "INVITE_TOKEN_RETURN_IN_RESPONSE": "true",
            "AUDIT_WS_REQUIRE_TENANT": "false",
            "API_KEY_SECRET_RETURN_IN_RESPONSE": "true",
            "AGENT_URL": "https://cdn.example.com/agent.js",
            "TRUST_PROXY_HEADERS": "true",
            "TRUSTED_PROXY_IPS": '["10.0.0.0/8","192.168.0.0/16"]',
            "TRUSTED_IP_HEADERS": '["X-Forwarded-For","X-Real-IP"]',
            "ALLOW_RAW_IP_SECURITY_ENDPOINTS": "true",
            "SECURITY_HEADERS_ENABLED": "false",
            "HSTS_MAX_AGE": "123",
            "HSTS_INCLUDE_SUBDOMAINS": "false",
            "HSTS_PRELOAD": "true",
            "X_FRAME_OPTIONS": "SAMEORIGIN",
            "REFERRER_POLICY": "no-referrer",
            "CSP_DEFAULT": "default-src 'self'",
            "INGEST_DEFAULT_RPM": "99",
            "INGEST_DEFAULT_BURST": "101",
            "INGEST_IP_RPM": "150",
            "INGEST_IP_BURST": "200",
            "INGEST_MAX_BODY_BYTES": "12345",
            "INGEST_INVALID_BAN_THRESHOLD": "11",
            "INGEST_INVALID_WINDOW_SECONDS": "22",
            "INGEST_BAN_SECONDS": "333",
            "INGEST_SECURITY_DEFAULT_RPM": "55",
            "INGEST_SECURITY_DEFAULT_BURST": "66",
            "INGEST_SECURITY_IP_RPM": "77",
            "INGEST_SECURITY_IP_BURST": "88",
            "INGEST_ABUSE_BAN_THRESHOLD": "9",
            "INGEST_ABUSE_WINDOW_SECONDS": "44",
            "INGEST_ABUSE_BAN_SECONDS": "555",
            "GEO_PROVIDER": "api",
            "GEO_DB_PATH": "/tmp/city.mmdb",
            "GEO_ASN_DB_PATH": "/tmp/asn.mmdb",
            "GEO_API_KEY": "geo-key",
            "GEO_API_BASE_URL": "https://geo.example.com",
            "GEO_ENRICHMENT_TTL_DAYS": "7",
            "ZERO_TRUST_API_KEY": "zt-key",
            "FRONTEND_BASE_URL": "https://app.example.com",
            "SSO_STATE_TTL_SECONDS": "120",
            "SSO_DISCOVERY_TIMEOUT_SECONDS": "2",
            "SSO_TOKEN_TIMEOUT_SECONDS": "3",
            "SSO_DISCOVERY_CACHE_SECONDS": "60",
        },
    )
    cfg = Settings(_env_file=None)
    assert cfg.ENVIRONMENT == "production"
    assert cfg.TENANT_HEADER_NAME == "X-Org"
    assert cfg.REQUIRE_TENANT_HEADER is False
    assert cfg.DEFAULT_TENANT_SLUG == "dev-tenant"
    assert cfg.ALLOW_MULTI_TENANT_DEV_BYPASS is True
    assert cfg.TENANT_STRICT_404 is False
    assert cfg.TENANT_CONTEXT_RESOLUTION_ORDER == ["jwt", "header"]
    assert cfg.INVITE_TOKEN_TTL_HOURS == 24
    assert cfg.INVITE_TOKEN_RETURN_IN_RESPONSE is True
    assert cfg.AUDIT_WS_REQUIRE_TENANT is False
    assert cfg.API_KEY_SECRET_RETURN_IN_RESPONSE is True
    assert cfg.AGENT_URL == "https://cdn.example.com/agent.js"
    assert cfg.TRUST_PROXY_HEADERS is True
    assert cfg.TRUSTED_PROXY_IPS == ["10.0.0.0/8", "192.168.0.0/16"]
    assert cfg.TRUSTED_IP_HEADERS == ["X-Forwarded-For", "X-Real-IP"]
    assert cfg.ALLOW_RAW_IP_SECURITY_ENDPOINTS is True
    assert cfg.SECURITY_HEADERS_ENABLED is False
    assert cfg.HSTS_MAX_AGE == 123
    assert cfg.HSTS_INCLUDE_SUBDOMAINS is False
    assert cfg.HSTS_PRELOAD is True
    assert cfg.X_FRAME_OPTIONS == "SAMEORIGIN"
    assert cfg.REFERRER_POLICY == "no-referrer"
    assert cfg.CSP_DEFAULT == "default-src 'self'"
    assert cfg.INGEST_DEFAULT_RPM == 99
    assert cfg.INGEST_DEFAULT_BURST == 101
    assert cfg.INGEST_IP_RPM == 150
    assert cfg.INGEST_IP_BURST == 200
    assert cfg.INGEST_MAX_BODY_BYTES == 12345
    assert cfg.INGEST_INVALID_BAN_THRESHOLD == 11
    assert cfg.INGEST_INVALID_WINDOW_SECONDS == 22
    assert cfg.INGEST_BAN_SECONDS == 333
    assert cfg.INGEST_SECURITY_DEFAULT_RPM == 55
    assert cfg.INGEST_SECURITY_DEFAULT_BURST == 66
    assert cfg.INGEST_SECURITY_IP_RPM == 77
    assert cfg.INGEST_SECURITY_IP_BURST == 88
    assert cfg.INGEST_ABUSE_BAN_THRESHOLD == 9
    assert cfg.INGEST_ABUSE_WINDOW_SECONDS == 44
    assert cfg.INGEST_ABUSE_BAN_SECONDS == 555
    assert cfg.GEO_PROVIDER == "api"
    assert cfg.GEO_DB_PATH == "/tmp/city.mmdb"
    assert cfg.GEO_ASN_DB_PATH == "/tmp/asn.mmdb"
    assert cfg.GEO_API_KEY == "geo-key"
    assert cfg.GEO_API_BASE_URL == "https://geo.example.com"
    assert cfg.GEO_ENRICHMENT_TTL_DAYS == 7
    assert cfg.DATABASE_URL == "sqlite:///:memory:"
    assert cfg.SECRET_KEY == "override"
    assert cfg.ZERO_TRUST_API_KEY == "zt-key"
    assert cfg.FRONTEND_BASE_URL == "https://app.example.com"
    assert cfg.SSO_STATE_TTL_SECONDS == 120
    assert cfg.SSO_DISCOVERY_TIMEOUT_SECONDS == 2
    assert cfg.SSO_TOKEN_TIMEOUT_SECONDS == 3
    assert cfg.SSO_DISCOVERY_CACHE_SECONDS == 60


def test_invite_ttl_must_be_positive(monkeypatch):
    Settings = _load_settings(monkeypatch)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, INVITE_TOKEN_TTL_HOURS=0)
