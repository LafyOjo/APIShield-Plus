from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from dataclasses import dataclass
from hashlib import sha1
from typing import Any, Protocol

from fastapi.encoders import jsonable_encoder

from app.core.config import settings
from app.core.metrics import record_cache_hit, record_cache_miss, record_cache_set


logger = logging.getLogger(__name__)


class CacheBackend(Protocol):
    def get(self, key: str) -> str | None:
        ...

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        ...

    def delete(self, key: str) -> None:
        ...

    def clear(self) -> None:
        ...


@dataclass
class _CacheEntry:
    expires_at: float | None
    value: str


class InMemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, _CacheEntry] = {}

    def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.expires_at is not None and time.monotonic() > entry.expires_at:
            self._store.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        expires_at = time.monotonic() + ttl if ttl and ttl > 0 else None
        self._store[key] = _CacheEntry(expires_at=expires_at, value=value)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()


class NullCache:
    def get(self, key: str) -> str | None:
        return None

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        return None

    def delete(self, key: str) -> None:
        return None

    def clear(self) -> None:
        return None


class RedisCache:
    def __init__(self, url: str) -> None:
        try:
            import redis  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("redis package is required for Redis cache backend") from exc
        self._client = redis.Redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> str | None:
        return self._client.get(key)

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        if ttl and ttl > 0:
            self._client.setex(key, ttl, value)
            return None
        self._client.set(key, value)
        return None

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def clear(self) -> None:
        prefix = f"{settings.CACHE_NAMESPACE}:"
        for key in self._client.scan_iter(f"{prefix}*"):
            self._client.delete(key)


_CACHE_BACKEND: CacheBackend | None = None
_CACHE_SERVICE: "CacheService" | None = None


def _resolve_backend_name() -> str:
    env_override = os.getenv("CACHE_BACKEND")
    if os.getenv("PYTEST_CURRENT_TEST") and env_override is None:
        return "none"
    if settings.CHAOS_CACHE_DOWN:
        return "none"
    return (env_override or settings.CACHE_BACKEND or "memory").lower()


def _get_backend() -> CacheBackend:
    global _CACHE_BACKEND
    if _CACHE_BACKEND is not None:
        return _CACHE_BACKEND
    backend_name = _resolve_backend_name()
    if backend_name in {"none", "disabled", "off"}:
        _CACHE_BACKEND = NullCache()
        return _CACHE_BACKEND
    if backend_name == "redis":
        if not settings.REDIS_URL:
            logger.warning("Redis cache enabled but REDIS_URL is missing; using memory cache.")
            _CACHE_BACKEND = InMemoryCache()
            return _CACHE_BACKEND
        try:
            _CACHE_BACKEND = RedisCache(settings.REDIS_URL)
            return _CACHE_BACKEND
        except Exception as exc:
            logger.warning("Failed to initialize Redis cache; using memory cache. %s", exc)
            _CACHE_BACKEND = InMemoryCache()
            return _CACHE_BACKEND
    _CACHE_BACKEND = InMemoryCache()
    return _CACHE_BACKEND


def _serialize(value: Any) -> str | None:
    try:
        encoded = jsonable_encoder(value)
        return json.dumps(encoded, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        return None


def _deserialize(payload: str) -> Any | None:
    try:
        return json.loads(payload)
    except Exception:
        return None


class CacheService:
    """
    Thin service wrapper around the configured backend with JSON serialization
    and cache metrics collection.
    """

    def __init__(
        self,
        *,
        backend: CacheBackend | None = None,
        default_ttl: int | None = None,
    ) -> None:
        self._backend = backend
        self._default_ttl = (
            settings.CACHE_DEFAULT_TTL_SECONDS if default_ttl is None else default_ttl
        )

    def _active_backend(self) -> CacheBackend:
        return self._backend or _get_backend()

    def get(self, key: str, *, cache_name: str = "default") -> Any | None:
        payload = self._active_backend().get(key)
        if payload is None:
            record_cache_miss(cache_name)
            return None
        value = _deserialize(payload)
        if value is None:
            record_cache_miss(cache_name)
            return None
        record_cache_hit(cache_name)
        return value

    def set(
        self,
        key: str,
        value: Any,
        *,
        ttl: int | None = None,
        cache_name: str = "default",
    ) -> None:
        payload = _serialize(value)
        if payload is None:
            return None
        effective_ttl = self._default_ttl if ttl is None else ttl
        self._active_backend().set(key, payload, ttl=effective_ttl)
        record_cache_set(cache_name, len(payload))
        return None

    def delete(self, key: str) -> None:
        self._active_backend().delete(key)

    def clear(self) -> None:
        self._active_backend().clear()


def get_cache_service() -> CacheService:
    global _CACHE_SERVICE
    if _CACHE_SERVICE is None:
        _CACHE_SERVICE = CacheService()
    return _CACHE_SERVICE


def cache_get(key: str, *, cache_name: str = "default") -> Any | None:
    return get_cache_service().get(key, cache_name=cache_name)


def cache_set(
    key: str,
    value: Any,
    *,
    ttl: int | None = None,
    cache_name: str = "default",
) -> None:
    return get_cache_service().set(key, value, ttl=ttl, cache_name=cache_name)


def cache_delete(key: str) -> None:
    get_cache_service().delete(key)


def cache_clear() -> None:
    get_cache_service().clear()


def reset_cache_backend() -> None:
    global _CACHE_BACKEND, _CACHE_SERVICE
    _CACHE_BACKEND = None
    _CACHE_SERVICE = None


def filters_hash(filters: dict[str, Any]) -> str:
    encoded = jsonable_encoder(filters)
    raw = json.dumps(encoded, sort_keys=True, separators=(",", ":"), default=str)
    return sha1(raw.encode("utf-8")).hexdigest()


def build_cache_key(
    prefix: str,
    *,
    tenant_id: int,
    db_scope: str | None = None,
    filters: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {}
    if db_scope:
        payload["db"] = db_scope
    if filters:
        payload.update(filters)
    suffix = filters_hash(payload) if payload else "v1"
    return f"{settings.CACHE_NAMESPACE}:tenant:{tenant_id}:{prefix}:{suffix}"


def _time_key_part(value: datetime | str | None) -> str:
    if value is None:
        return "none"
    if isinstance(value, datetime):
        raw = value.isoformat()
    else:
        raw = str(value)
    return raw.replace(":", "_")


def build_tenant_query_cache_key(
    prefix: str,
    *,
    tenant_id: int,
    website_id: int | None,
    env_id: int | None,
    from_ts: datetime | str | None,
    to_ts: datetime | str | None,
    filters: dict[str, Any] | None = None,
    db_scope: str | None = None,
) -> str:
    """
    Build a cache key for tenant-scoped query results.

    Required dimensions:
    - tenant_id
    - website_id
    - env_id
    - time range (from/to)
    - filters hash
    """
    payload: dict[str, Any] = {
        "website_id": website_id,
        "env_id": env_id,
        "from": from_ts,
        "to": to_ts,
    }
    if db_scope:
        payload["db"] = db_scope
    if filters:
        payload.update(filters)
    filter_digest = filters_hash(payload)
    website_part = website_id if website_id is not None else "all"
    env_part = env_id if env_id is not None else "all"
    from_part = _time_key_part(from_ts)
    to_part = _time_key_part(to_ts)
    return (
        f"{settings.CACHE_NAMESPACE}:tenant:{tenant_id}:website:{website_part}:"
        f"env:{env_part}:from:{from_part}:to:{to_part}:{prefix}:{filter_digest}"
    )


def db_scope_id(db) -> str | None:
    try:
        bind = db.get_bind()
    except Exception:
        return None
    if bind is None:
        return None
    try:
        url = str(bind.url)
    except Exception:
        return None
    return sha1(url.encode("utf-8")).hexdigest()[:12]
