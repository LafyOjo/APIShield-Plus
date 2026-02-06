# Central place for all configurable settings. We use Pydantic's
# BaseSettings so values can be read from env vars or a .env file.
# This keeps deployment flexible without hardcoding secrets.

import json
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def safe_json_loads(value):
    try:
        return json.loads(value)
    except Exception:
        return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_json_loads=safe_json_loads,
    )

    # Environment marker used for secure defaults and startup checks.
    # Accepted values: development, staging, production.
    ENVIRONMENT: str = "development"
    # Launch-mode toggle: enable strict production posture.
    # When enabled, demo-only behaviors are disabled.
    LAUNCH_MODE: bool = False

    # Core DB connection string, like sqlite:///./app.db or Postgres URL.
    # Needed by SQLAlchemy to connect to the persistence layer.
    DATABASE_URL: str

    # Secret key used for signing JWTs and other crypto operations.
    # Must be kept private in production.
    SECRET_KEY: str

    # JWT algorithm to use. Default HS256 (symmetric HMAC-SHA256).
    ALGORITHM: str = "HS256"

    # How long issued access tokens are valid, in minutes.
    # Default: 15 mins.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    SUPPORT_VIEW_TOKEN_TTL_MINUTES: int = 10

    # OIDC issuer and audience used to validate tokens from an IdP.
    # Defaults to demo Keycloak realm setup.
    OIDC_ISSUER: str = "https://keycloak.example.com/realms/demo"
    OIDC_AUDIENCE: str = "demo-api"

    # Rate limiting: max fails allowed + sliding window size (seconds).
    # Protects against brute force / stuffing attacks.
    FAIL_LIMIT: int = 5
    FAIL_WINDOW_SECONDS: int = 60

    # Tenancy: header resolution and enforcement
    TENANT_HEADER_NAME: str = "X-Tenant-ID"
    REQUIRE_TENANT_HEADER: bool = True
    DEFAULT_TENANT_SLUG: Optional[str] = None
    ALLOW_MULTI_TENANT_DEV_BYPASS: bool = False
    TENANT_STRICT_404: bool = True
    TENANT_CONTEXT_RESOLUTION_ORDER: List[str] = Field(
        default_factory=lambda: ["header", "jwt", "default"]
    )

    # Invitation and security timing
    INVITE_TOKEN_TTL_HOURS: int = Field(default=72, gt=0)
    INVITE_TOKEN_RETURN_IN_RESPONSE: bool = False
    AUDIT_WS_REQUIRE_TENANT: bool = True

    # API key responses and embed snippet configuration
    API_KEY_SECRET_RETURN_IN_RESPONSE: bool = False
    AGENT_URL: str = "https://cdn.yourapp.com/agent.js"
    BADGE_SIGNATURE_TTL_SECONDS: int = 300
    BADGE_JS_CACHE_SECONDS: int = 60
    BADGE_DATA_CACHE_SECONDS: int = 60

    # Public trust score proof settings.
    TRUST_SCORE_SIGNING_PRIVATE_KEY: Optional[str] = None
    TRUST_SCORE_SIGNING_PUBLIC_KEY: Optional[str] = None
    TRUST_SCORE_SIGNING_KEY_ID: Optional[str] = None
    TRUST_SCORE_CACHE_SECONDS: int = 60
    TRUST_SCORE_RPM: int = 120
    TRUST_SCORE_BURST: int = 120
    TRUST_SCORE_ABUSE_THRESHOLD: int = 20
    TRUST_SCORE_BAN_SECONDS: int = 600

    # Performance profiling (opt-in).
    PERF_PROFILING: bool = False
    PERF_SLOW_QUERY_MS: int = 200
    PERF_SLOW_QUERY_MAX_PER_REQUEST: int = 5

    # Chaos testing toggles (staging-only).
    CHAOS_DB_LATENCY_MS: int = 0
    CHAOS_CACHE_DOWN: bool = False

    # Caching configuration.
    # CACHE_BACKEND: memory | redis | none
    CACHE_BACKEND: str = "memory"
    CACHE_NAMESPACE: str = "apishield"
    CACHE_DEFAULT_TTL_SECONDS: int = 60
    CACHE_TTL_MAP_SUMMARY: int = 60
    CACHE_TTL_MAP_DRILLDOWN: int = 60
    CACHE_TTL_REVENUE_LEAKS: int = 60
    CACHE_TTL_TRUST_SNAPSHOTS: int = 60
    CACHE_TTL_PORTFOLIO_SUMMARY: int = 60
    CACHE_TTL_INCIDENTS_LIST: int = 30
    CACHE_TTL_INCIDENT_DETAIL: int = 30
    REDIS_URL: Optional[str] = None

    # Proxy/client IP extraction settings
    TRUST_PROXY_HEADERS: bool = False
    TRUSTED_PROXY_IPS: List[str] = Field(default_factory=list)
    TRUSTED_IP_HEADERS: List[str] = Field(
        default_factory=lambda: [
            "CF-Connecting-IP",
            "X-Forwarded-For",
            "X-Real-IP",
        ]
    )

    # Security analytics endpoints
    ALLOW_RAW_IP_SECURITY_ENDPOINTS: bool = False

    # Security headers (CSP/HSTS/etc.)
    SECURITY_HEADERS_ENABLED: bool = True
    HSTS_MAX_AGE: int = 31536000
    HSTS_INCLUDE_SUBDOMAINS: bool = True
    HSTS_PRELOAD: bool = False
    X_FRAME_OPTIONS: str = "DENY"
    REFERRER_POLICY: str = "strict-origin-when-cross-origin"
    CSP_DEFAULT: str = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "img-src 'self' data:; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'"
    )

    # Ingestion rate limiting + abuse protection
    INGEST_DEFAULT_RPM: int = 120
    INGEST_DEFAULT_BURST: int = 120
    INGEST_IP_RPM: int = 300
    INGEST_IP_BURST: int = 300
    INGEST_MAX_BODY_BYTES: int = 65536
    INGEST_INVALID_BAN_THRESHOLD: int = 20
    INGEST_INVALID_WINDOW_SECONDS: int = 60
    INGEST_BAN_SECONDS: int = 600
    INGEST_SECURITY_DEFAULT_RPM: int = 60
    INGEST_SECURITY_DEFAULT_BURST: int = 60
    INGEST_SECURITY_IP_RPM: int = 120
    INGEST_SECURITY_IP_BURST: int = 120
    INGEST_ABUSE_BAN_THRESHOLD: int = 10
    INGEST_ABUSE_WINDOW_SECONDS: int = 60
    INGEST_ABUSE_BAN_SECONDS: int = 900
    INGEST_MAX_BATCH_EVENTS: int = 50
    INGEST_SAMPLING_DEFAULT_RATE: float = 1.0

    # Data export configuration (warehouse connectors).
    EXPORT_TARGET: str = "local"
    EXPORT_LOCAL_DIR: str = "./exports"
    EXPORT_DEFAULT_LOOKBACK_HOURS: int = 24

    # Job queue settings (worker partitions + fairness).
    JOB_QUEUE_LOCK_TIMEOUT_SECONDS: int = 300
    JOB_QUEUE_POLL_INTERVAL_SECONDS: int = 2
    QUEUE_TENANT_RPM_STANDARD: int = 60
    QUEUE_TENANT_BURST_STANDARD: int = 5
    QUEUE_TENANT_MAX_IN_FLIGHT_STANDARD: int = 1
    QUEUE_TENANT_RPM_BULK: int = 10
    QUEUE_TENANT_BURST_BULK: int = 2
    QUEUE_TENANT_MAX_IN_FLIGHT_BULK: int = 1

    # Demo data seeding / expiry.
    DEMO_DATA_RETENTION_DAYS: int = 7

    # Onboarding email nudges.
    EMAILS_ENABLED: bool = True
    ONBOARDING_NO_EVENTS_HOURS: int = 2

    # Affiliate program settings.
    AFFILIATE_REFUND_WINDOW_DAYS: int = 14

    # Multi-region readiness (data residency).
    DEFAULT_TENANT_REGION: str = "us"
    REGION_DB_URLS: dict = Field(default_factory=dict)
    REGION_EXPORT_TARGETS: dict = Field(default_factory=dict)
    PLATFORM_AUDIT_TENANT_ID: Optional[int] = None

    # External integration encryption (base64 Fernet key recommended).
    INTEGRATION_ENCRYPTION_KEY: Optional[str] = None

    # SSO / OIDC settings.
    SSO_STATE_TTL_SECONDS: int = 600
    SSO_DISCOVERY_TIMEOUT_SECONDS: int = 5
    SSO_TOKEN_TIMEOUT_SECONDS: int = 5
    SSO_DISCOVERY_CACHE_SECONDS: int = 300
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # Geo enrichment strategy and configuration.
    # GEO_PROVIDER: "local" or "api"
    GEO_PROVIDER: str = "local"
    GEO_DB_PATH: str = "/data/geo/GeoLite2-City.mmdb"
    GEO_ASN_DB_PATH: str = "/data/geo/GeoLite2-ASN.mmdb"
    GEO_API_KEY: Optional[str] = None
    GEO_API_BASE_URL: Optional[str] = None
    GEO_ENRICHMENT_TTL_DAYS: int = 30

    @field_validator("TENANT_CONTEXT_RESOLUTION_ORDER", mode="before")
    @classmethod
    def _parse_resolution_order(cls, value):
        if isinstance(value, str):
            parts = [p.strip() for p in value.split(",") if p.strip()]
            return parts
        return value

    @field_validator("TRUSTED_PROXY_IPS", "TRUSTED_IP_HEADERS", mode="before")
    @classmethod
    def _parse_list_values(cls, value):
        if isinstance(value, str):
            parts = [p.strip() for p in value.split(",") if p.strip()]
            return parts
        return value

    # Toggle SQLAlchemy echo logs. Useful for debugging queries locally.
    DB_ECHO: bool = False

    # Integration flags with the demo shop (register/login sync).
    # Makes the app optionally hook into a front-end demo service.
    REGISTER_WITH_DEMOSHOP: bool = False
    LOGIN_WITH_DEMOSHOP: bool = False
    DEMO_SHOP_URL: str = "http://localhost:3005"

    # Experimental anomaly detection middleware switch + model choice.
    # Defaults to LOF but can be changed via env var.
    ANOMALY_DETECTION: bool = False
    ANOMALY_MODEL: str = "lof"

    # Re-auth enforcement setting (force login per request if True).
    REAUTH_PER_REQUEST: bool = False

    # Zero Trust API key for APIShield+ flows.
    ZERO_TRUST_API_KEY: Optional[str] = None

    # Where Prometheus is expected to live inside k8s cluster.
    # Metrics scrapers point here.
    PROMETHEUS_URL: str = "http://kube-prom-kube-prometheus-prometheus.monitoring.svc:9090"

    # Incident status automation thresholds.
    INCIDENT_INVESTIGATING_DELTA_RATE: float = 0.05
    INCIDENT_MITIGATION_RECOVERY_RATIO: float = 0.7
    INCIDENT_MITIGATION_ERROR_DROP: float = 0.05
    INCIDENT_MITIGATION_THREAT_DROP: int = 1
    INCIDENT_RESOLVE_COOLDOWN_HOURS: int = 6
    INCIDENT_RESOLVE_CONVERSION_TOLERANCE: float = 0.05

    # Stripe billing configuration.
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_PRICE_ID_PRO: Optional[str] = None
    STRIPE_PRICE_ID_BUSINESS: Optional[str] = None
    STRIPE_PRICE_ID_ENTERPRISE: Optional[str] = None
    APP_BASE_URL: Optional[str] = None


# Instantiate a single settings object for app-wide import.
# Any module can just `from app.core.config import settings`.
settings = Settings()
