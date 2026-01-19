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

    # Core DB connection string, like sqlite:///./app.db or Postgres URL.
    # Needed by SQLAlchemy to connect to the persistence layer.
    DATABASE_URL: str

    # Secret key used for signing JWTs and other crypto operations.
    # Must be kept private in production.
    SECRET_KEY: str

    # JWT algorithm to use. Default HS256 (symmetric HMAC-SHA256).
    ALGORITHM: str = "HS256"

    # How long issued access tokens are valid, in minutes.
    # Default: 30 mins.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

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

    # Ingestion rate limiting + abuse protection
    INGEST_DEFAULT_RPM: int = 120
    INGEST_DEFAULT_BURST: int = 120
    INGEST_IP_RPM: int = 300
    INGEST_IP_BURST: int = 300
    INGEST_MAX_BODY_BYTES: int = 65536
    INGEST_INVALID_BAN_THRESHOLD: int = 20
    INGEST_INVALID_WINDOW_SECONDS: int = 60
    INGEST_BAN_SECONDS: int = 600

    # External integration encryption (base64 Fernet key recommended).
    INTEGRATION_ENCRYPTION_KEY: Optional[str] = None

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

    # Zero Trust API key placeholder for APIShield+ flows.
    ZERO_TRUST_API_KEY: str = "demo-key"

    # Where Prometheus is expected to live inside k8s cluster.
    # Metrics scrapers point here.
    PROMETHEUS_URL: str = "http://kube-prom-kube-prometheus-prometheus.monitoring.svc:9090"


# Instantiate a single settings object for app-wide import.
# Any module can just `from app.core.config import settings`.
settings = Settings()
