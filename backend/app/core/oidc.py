from __future__ import annotations

import secrets
import time
from urllib.parse import urlencode

import requests
from jose import JWTError, jwt

from app.core.config import settings


DEFAULT_SCOPES = "openid email profile"
STATE_ALGORITHM = "HS256"

_DISCOVERY_CACHE: dict[str, tuple[float, dict[str, str]]] = {}


def _state_ttl_seconds() -> int:
    return int(getattr(settings, "SSO_STATE_TTL_SECONDS", 600))


def _discovery_timeout_seconds() -> int:
    return int(getattr(settings, "SSO_DISCOVERY_TIMEOUT_SECONDS", 5))


def _token_timeout_seconds() -> int:
    return int(getattr(settings, "SSO_TOKEN_TIMEOUT_SECONDS", 5))


def _discovery_cache_ttl_seconds() -> int:
    return int(getattr(settings, "SSO_DISCOVERY_CACHE_SECONDS", 300))


def create_state_token(tenant_id: int, *, nonce: str, next_path: str | None) -> str:
    now = int(time.time())
    payload = {
        "tenant_id": tenant_id,
        "nonce": nonce,
        "next": next_path,
        "iat": now,
        "exp": now + _state_ttl_seconds(),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=STATE_ALGORITHM)


def decode_state_token(state: str) -> dict[str, object]:
    try:
        return jwt.decode(state, settings.SECRET_KEY, algorithms=[STATE_ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid SSO state") from exc


def sanitize_next_path(next_path: str | None) -> str | None:
    if not next_path:
        return None
    if next_path.startswith(("http://", "https://")):
        return None
    if not next_path.startswith("/"):
        return None
    return next_path


def fetch_discovery(issuer_url: str) -> dict[str, str]:
    issuer = issuer_url.rstrip("/")
    cached = _DISCOVERY_CACHE.get(issuer)
    if cached and (time.time() - cached[0]) < _discovery_cache_ttl_seconds():
        return cached[1]
    url = f"{issuer}/.well-known/openid-configuration"
    resp = requests.get(url, timeout=_discovery_timeout_seconds())
    resp.raise_for_status()
    payload = resp.json()
    discovery = {
        "issuer": payload.get("issuer", issuer),
        "authorization_endpoint": payload.get("authorization_endpoint"),
        "token_endpoint": payload.get("token_endpoint"),
        "jwks_uri": payload.get("jwks_uri"),
    }
    _DISCOVERY_CACHE[issuer] = (time.time(), discovery)
    return discovery


def build_authorize_url(
    *,
    discovery: dict[str, str],
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str,
    nonce: str,
) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope or DEFAULT_SCOPES,
        "state": state,
        "nonce": nonce,
    }
    return f"{discovery['authorization_endpoint']}?{urlencode(params)}"


def exchange_code_for_tokens(
    *,
    discovery: dict[str, str],
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
) -> dict[str, object]:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }
    resp = requests.post(discovery["token_endpoint"], data=data, timeout=_token_timeout_seconds())
    resp.raise_for_status()
    return resp.json()


def verify_id_token(
    *,
    id_token: str,
    discovery: dict[str, str],
    client_id: str,
    nonce: str,
) -> dict[str, object]:
    unverified_header = jwt.get_unverified_header(id_token)
    jwks_resp = requests.get(discovery["jwks_uri"], timeout=_discovery_timeout_seconds())
    jwks_resp.raise_for_status()
    jwks = jwks_resp.json()
    rsa_key = None
    for key in jwks.get("keys", []):
        if key.get("kid") == unverified_header.get("kid"):
            rsa_key = {
                "kty": key.get("kty"),
                "kid": key.get("kid"),
                "use": key.get("use"),
                "n": key.get("n"),
                "e": key.get("e"),
            }
            break
    if not rsa_key:
        raise ValueError("Unable to find matching JWKS key")
    claims = jwt.decode(
        id_token,
        rsa_key,
        algorithms=[unverified_header.get("alg", "RS256")],
        audience=client_id,
        issuer=discovery["issuer"],
    )
    if claims.get("nonce") != nonce:
        raise ValueError("Invalid OIDC nonce")
    return claims


def generate_nonce() -> str:
    return secrets.token_urlsafe(24)
