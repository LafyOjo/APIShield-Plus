# This file bootstraps the FastAPI app, wires up middlewares for
# logging/security, sets up CORS, and includes all the routers.
# It’s the heart of the project where everything is connected.

from fastapi import APIRouter, FastAPI, Response
from fastapi.responses import JSONResponse
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
from app.tenancy.middleware import RequestContextMiddleware
from app.core.re_auth import ReAuthMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.startup_checks import run_startup_checks
from app.core.versioning import API_PREFIX, API_V1_PREFIX
from app.entitlements.enforcement import FeatureNotEnabled, PlanLimitExceeded, RangeClampedNotice

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
from app.api.api_keys import router as api_keys_router
from app.api.invites import router as invites_router
from app.api.tenant_settings import router as tenant_settings_router
from app.api.usage import router as usage_router
from app.api.data_retention import router as data_retention_router
from app.api.tenant_retention import router as tenant_retention_router
from app.api.entitlements import router as entitlements_router
from app.api.domain_verification import router as domain_verification_router
from app.api.project_tags import router as project_tags_router
from app.api.external_integrations import router as external_integrations_router
from app.api.exports import router as exports_router
from app.api.admin import router as admin_router
from app.api.status_admin import router as status_admin_router
from app.api.status_page import router as status_page_router
from app.api.user_profile import router as user_profile_router
from app.api.memberships import router as memberships_router
from app.api.tenants import router as tenants_router
from app.api.me import router as me_router
from app.api.websites import router as websites_router
from app.api.ingest import router as ingest_router
from app.api.ingest_security import router as ingest_security_router
from app.api.analytics import router as analytics_router
from app.api.map import router as map_router
from app.api.incidents import router as incidents_router
from app.api.trust import router as trust_router
from app.api.revenue_leaks import router as revenue_leaks_router
from app.api.prescriptions import router as prescriptions_router
from app.api.notifications import router as notifications_router
from app.api.sso import router as sso_router
from app.api.oidc import router as oidc_router
from app.api.saml import router as saml_router
from app.api.scim_config import router as scim_config_router
from app.api.scim import router as scim_router
from app.api.onboarding import router as onboarding_router
from app.api.user_tours import router as user_tours_router
from app.api.demo import router as demo_router
from app.api.docs import router as docs_router

# Billing router depends on optional Stripe install.
try:
    from app.api.billing import router as billing_router
except Exception:
    billing_router = None

# Create DB tables right away so the app doesn’t hit missing
# schema issues later. This runs once on startup.
if os.getenv("SKIP_MIGRATIONS") != "1":
    Base.metadata.create_all(bind=engine)

# Spin up the FastAPI app. Title shows in Swagger docs.
app = FastAPI(title="APIShield+")


@app.on_event("startup")
def _run_security_startup_checks() -> None:
    run_startup_checks()


@app.exception_handler(PlanLimitExceeded)
def handle_plan_limit(_request, exc: PlanLimitExceeded):
    response = JSONResponse(status_code=exc.status_code, content=exc.to_payload())
    response.headers["X-Error-Code"] = exc.code
    return response


@app.exception_handler(FeatureNotEnabled)
def handle_feature_disabled(_request, exc: FeatureNotEnabled):
    response = JSONResponse(status_code=exc.status_code, content=exc.to_payload())
    response.headers["X-Error-Code"] = exc.code
    return response


@app.exception_handler(RangeClampedNotice)
def handle_range_clamped(_request, exc: RangeClampedNotice):
    response = JSONResponse(status_code=exc.status_code, content=exc.to_payload())
    response.headers["X-Error-Code"] = exc.code
    return response

# Observability and logging layers
# These middlewares capture logs, request metrics, and access
# information so you can troubleshoot and track usage easily.
app.add_middleware(APILoggingMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

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

# Routers grouped by version + compatibility
api_v1 = APIRouter(prefix=API_V1_PREFIX)
api_legacy = APIRouter(prefix=API_PREFIX)
api_root = APIRouter(prefix="")

routers = [
    score_router,
    alerts_router,
    auth_router,
    config_router,
    security_router,
    user_stats_router,
    events_router,
    last_logins_router,
    access_logs_router,
    audit_router,
    auth_events_router,
    api_keys_router,
    invites_router,
    tenant_settings_router,
    usage_router,
    data_retention_router,
    tenant_retention_router,
    entitlements_router,
    domain_verification_router,
    project_tags_router,
    external_integrations_router,
    exports_router,
    admin_router,
    status_admin_router,
    user_profile_router,
    memberships_router,
    tenants_router,
    websites_router,
    ingest_router,
    ingest_security_router,
    analytics_router,
    map_router,
    incidents_router,
    trust_router,
    revenue_leaks_router,
    prescriptions_router,
    notifications_router,
    sso_router,
    scim_config_router,
    onboarding_router,
    user_tours_router,
    demo_router,
    docs_router,
]

if billing_router is not None:
    routers.append(billing_router)

for r in routers:
    api_v1.include_router(r)
    api_legacy.include_router(r)
    api_root.include_router(r)

api_v1.include_router(me_router)
api_root.include_router(oidc_router)
api_root.include_router(saml_router)
api_root.include_router(scim_router)
api_root.include_router(status_page_router)

# Optional router for credential stuffing stats
try:
    from app.api.credential_stuffing import router as credential_stuffing_router

    api_v1.include_router(credential_stuffing_router)
    api_legacy.include_router(credential_stuffing_router)
    api_root.include_router(credential_stuffing_router)
except Exception:
    pass

app.include_router(api_v1)
app.include_router(api_legacy)
app.include_router(api_root)

# Attach request context (request_id, client_ip, request_meta) early.
app.add_middleware(RequestContextMiddleware)

# /metrics endpoint (Prometheus scraping)
# Exposes metrics in the standard Prometheus text format so you
# can monitor app health and performance.
@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# /ping endpoint and versioned health
@app.get("/ping")
@app.get(f"{API_V1_PREFIX}/health")
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
