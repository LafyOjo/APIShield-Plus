# Central place for all configurable settings. We use Pydantic’s
# BaseSettings so values can be read from env vars or a .env file.
# This keeps deployment flexible without hardcoding secrets.

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
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

    class Config:
        # Tell Pydantic to read from a .env file by default.
        # This means local dev can work without exporting env vars.
        env_file = ".env"
        env_file_encoding = "utf-8"


# Instantiate a single settings object for app-wide import.
# Any module can just `from app.core.config import settings`.
settings = Settings()
