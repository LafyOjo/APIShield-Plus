import os

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("ZERO_TRUST_API_KEY", "")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.main import app


client = TestClient(app)

PUBLIC_PATH_PREFIXES = {
    "/docs",
    "/docs/oauth2-redirect",
    "/docs/openapi.yaml",
    "/openapi.json",
    "/openapi.yaml",
    "/metrics",
    "/ingest",
    "/api/ingest",
    "/api/v1/ingest",
}

PUBLIC_METHOD_ROUTES = {
    "/ping": {"GET"},
    "/api/v1/health": {"GET"},
    "/login": {"POST"},
    "/api/login": {"POST"},
    "/api/v1/login": {"POST"},
    "/register": {"POST"},
    "/api/register": {"POST"},
    "/api/v1/register": {"POST"},
    "/api/token": {"POST"},
    "/api/api/token": {"POST"},
    "/api/v1/api/token": {"POST"},
    "/score": {"POST"},
    "/api/score": {"POST"},
    "/api/v1/score": {"POST"},
    "/events/auth": {"POST"},
    "/api/events/auth": {"POST"},
    "/api/v1/events/auth": {"POST"},
    "/auth/oidc/status": {"GET"},
    "/auth/oidc/start": {"GET"},
    "/auth/oidc/callback": {"GET"},
    "/auth/saml/metadata": {"GET"},
    "/auth/saml/acs": {"POST"},
}


def _is_public_route(path: str, methods: set[str]) -> bool:
    if any(path == prefix or path.startswith(prefix + "/") for prefix in PUBLIC_PATH_PREFIXES):
        return True
    allowed = PUBLIC_METHOD_ROUTES.get(path)
    if not allowed:
        return False
    normalized_methods = {method for method in methods if method not in {"HEAD", "OPTIONS"}}
    return normalized_methods.issubset(allowed)


def test_routes_have_auth_or_rbac_dependencies():
    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if _is_public_route(route.path, route.methods or set()):
            continue
        labels = [
            getattr(dep.call, "__qualname__", getattr(dep.call, "__name__", str(dep.call)))
            for dep in route.dependant.dependencies
        ]
        has_auth = any("get_current_user" in label for label in labels)
        has_rbac = any("require_roles" in label or "require_tenant_context" in label for label in labels)
        if not (has_auth or has_rbac):
            missing.append((route.path, route.methods))

    assert not missing, f"Missing auth/RBAC dependencies on routes: {missing}"
