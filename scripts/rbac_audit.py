from __future__ import annotations

from fastapi.routing import APIRoute

from app.main import app


PUBLIC_PATH_PREFIXES = {
    "/docs",
    "/docs/oauth2-redirect",
    "/openapi.json",
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


def _dependency_labels(route: APIRoute) -> list[str]:
    labels = []
    for dep in route.dependant.dependencies:
        call = dep.call
        name = getattr(call, "__qualname__", getattr(call, "__name__", str(call)))
        labels.append(name)
    return labels


def main() -> int:
    issues = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if _is_public_route(route.path, route.methods or set()):
            continue
        labels = _dependency_labels(route)
        has_auth = any("get_current_user" in label for label in labels)
        has_rbac = any("require_roles" in label or "require_tenant_context" in label for label in labels)
        if not has_auth and not has_rbac:
            issues.append((route.path, route.methods))

    if issues:
        print("RBAC audit: endpoints missing auth/tenant dependencies")
        for path, methods in issues:
            print(f"- {sorted(methods)} {path}")
        return 1

    print("RBAC audit: no missing auth dependencies detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
