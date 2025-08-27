# This file bootstraps the FastAPI app, wires up middlewares for
# logging/security, sets up CORS, and includes all the routers.
# It’s the heart of the project where everything is connected.

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
import os
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from app.core.db import Base, engine

# Import all middleware layers for logging and security
from app.core.zero_trust import ZeroTrustMiddleware
from app.core.logging import APILoggingMiddleware
from app.core.access_log import AccessLogMiddleware
from app.core.anomaly import AnomalyDetectionMiddleware
from app.core.policy import PolicyEngineMiddleware
from app.core.metrics import MetricsMiddleware
from app.core.re_auth import ReAuthMiddleware

# Bring in all routers (grouped by feature area)
from app.api.score import router as score_router
from app.api.alerts import router as alerts_router
from app.api.auth import router as auth_router
from app.api.config import router as config_router
from app.api.security import router as security_router
from app.api.user_stats import router as user_stats_router
from app.api.events import router as events_router
from app.api.last_logins import router as last_logins_router
from app.api.access_logs import router as access_logs_router
from app.api.audit import router as audit_router
from app.api.auth_events import router as auth_events_router

# Create DB tables right away so the app doesn’t hit missing
# schema issues later. This runs once on startup.
Base.metadata.create_all(bind=engine)

# Spin up the FastAPI app. Title shows in Swagger docs.
app = FastAPI(title="APIShield+")


# Observability and logging layers
# These middlewares capture logs, request metrics, and access
# information so you can troubleshoot and track usage easily.
app.add_middleware(APILoggingMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(AccessLogMiddleware)

# Security middleware stack
# Layers are ordered: API key checks, per-request password guard,
# and IP-based policy enforcement. Together they harden the API.
app.add_middleware(ZeroTrustMiddleware)   # requires X-API-Key when configured
app.add_middleware(ReAuthMiddleware)      # per-request password guard
app.add_middleware(PolicyEngineMiddleware)

# Optional anomaly detection
# If the env var is set, suspicious requests get flagged before
# they even reach business logic.
if os.getenv("ANOMALY_DETECTION", "false").lower() == "true":
    app.add_middleware(AnomalyDetectionMiddleware)

# Routers for different feature areas
# Each router organizes endpoints under a clean prefix so the
# API feels modular and easy to explore in Swagger UI.
app.include_router(score_router)            # /score
app.include_router(alerts_router)           # /api/alerts
app.include_router(auth_router)             # /register, /login, /api/token
app.include_router(config_router)           # /config
app.include_router(security_router)         # /api/security
app.include_router(user_stats_router)       # /api/user-calls
app.include_router(events_router)           # /api/events
app.include_router(last_logins_router)      # /api/last-logins
app.include_router(access_logs_router)      # /api/access-logs
app.include_router(audit_router)            # /api/audit/log
app.include_router(auth_events_router)      # /events/auth

# Optional router for credential stuffing stats
# We import it safely with a try/except in case the file doesn’t
# exist (keeps deployments flexible).
try:
    from app.api.credential_stuffing import router as credential_stuffing_router
    app.include_router(credential_stuffing_router)   # /api/credential-stuffing-stats
except Exception:
    pass

# /metrics endpoint (Prometheus scraping)
# Exposes metrics in the standard Prometheus text format so you
# can monitor app health and performance.
@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# /ping endpoint
# Simple liveness check; responds with "pong". Useful for health
# probes, scripts, and debugging.
@app.get("/ping")
def ping():
    return {"message": "pong"}


# CORS setup
# Allows frontends (like local dev or Raspberry Pi dashboards)
# to hit the API without running into browser CORS errors.
app.add_middleware(
    CORSMiddleware,
    # accept http or https, localhost or 127.0.0.1, any port
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    # keep a short explicit allowlist for anything not covered by the regex
    allow_origins=[
        "http://raspberrypi:3000",
        "http://raspberrypi.local:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],     # lets browser send Authorization, X-API-Key, X-Reauth-Password, etc.
    expose_headers=["*"],
    max_age=86400,           # cache preflights
)
