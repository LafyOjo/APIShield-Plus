import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4


EVENT_TYPES = [
    "page_view",
    "click",
    "scroll",
    "form_submit",
    "error",
    "performance",
]

SECURITY_EVENT_TYPES = [
    "login_attempt_succeeded",
    "login_attempt_failed",
    "csp_violation",
    "credential_stuffing",
]

SECURITY_SEVERITY = {
    "login_attempt_succeeded": "low",
    "login_attempt_failed": "medium",
    "csp_violation": "medium",
    "credential_stuffing": "high",
}

DEFAULT_EVENT_MIX = [
    {"type": "page_view", "weight": 60},
    {"type": "click", "weight": 15},
    {"type": "scroll", "weight": 10},
    {"type": "form_submit", "weight": 5},
    {"type": "error", "weight": 5},
    {"type": "performance", "weight": 4},
    {"type": "login_attempt_succeeded", "weight": 1},
    {"type": "login_attempt_failed", "weight": 1},
    {"type": "csp_violation", "weight": 1},
]

DEFAULT_PATH_POOL = [
    "/",
    "/pricing",
    "/checkout",
    "/login",
    "/signup",
    "/docs",
    "/settings",
]

DEFAULT_REFERRERS = [
    "https://google.com",
    "https://news.ycombinator.com",
    "https://twitter.com",
    "https://linkedin.com",
    None,
]


@dataclass(frozen=True)
class TargetConfig:
    api_key: str
    domain: str
    weight: int = 1
    api_secret: str | None = None


@dataclass(frozen=True)
class EventGeneratorConfig:
    event_mix: list[dict[str, Any]]
    path_pool: list[str]
    referrers: list[str | None]
    session_pool_size: int = 1000


class SessionPool:
    def __init__(self, size: int, *, rng: random.Random):
        self._rng = rng
        self._pool = [f"s_{uuid4()}" for _ in range(max(1, size))]

    def pick(self) -> str:
        return self._rng.choice(self._pool)


def _normalize_mix(event_mix: Iterable[dict[str, Any]]) -> list[tuple[str, int]]:
    normalized = []
    for entry in event_mix:
        if not isinstance(entry, dict):
            continue
        event_type = str(entry.get("type") or "").strip()
        if event_type not in EVENT_TYPES and event_type not in SECURITY_EVENT_TYPES:
            continue
        weight = int(entry.get("weight") or 0)
        if weight <= 0:
            continue
        normalized.append((event_type, weight))
    if not normalized:
        normalized = [(entry["type"], entry["weight"]) for entry in DEFAULT_EVENT_MIX]
    return normalized


def _weighted_choice(pairs: list[tuple[str, int]], *, rng: random.Random) -> str:
    total = sum(weight for _, weight in pairs)
    pick = rng.uniform(0, total)
    cursor = 0
    for value, weight in pairs:
        cursor += weight
        if pick <= cursor:
            return value
    return pairs[-1][0]


def _default_meta(event_type: str) -> dict[str, Any] | None:
    if event_type == "click":
        return {"tag": "button", "id": "cta", "classes": "btn primary"}
    if event_type == "scroll":
        return {"depth": 80}
    if event_type == "form_submit":
        return {"form_id": "signup", "form_action": "/signup", "form_method": "post"}
    if event_type == "error":
        return {"message": "TypeError: undefined is not a function", "source": "app.js"}
    if event_type == "performance":
        return {"ttfb_ms": 120, "fcp_ms": 850}
    return None


def _security_meta(event_type: str) -> dict[str, Any] | None:
    if event_type == "csp_violation":
        return {"directive": "script-src", "blocked_uri": "https://evil.example.com"}
    if event_type == "credential_stuffing":
        return {"ip_reputation": "suspicious", "attempts": 25}
    return None


def build_security_event(
    *,
    event_type: str,
    path: str,
    session_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    timestamp = (now or datetime.now(timezone.utc)).isoformat()
    severity = SECURITY_SEVERITY.get(event_type, "medium")
    status_code = 200
    if event_type == "login_attempt_failed":
        status_code = 401
    return {
        "ts": timestamp,
        "event_type": event_type,
        "severity": severity,
        "request_path": path,
        "method": "POST" if "login" in event_type else "GET",
        "status_code": status_code,
        "session_id": session_id,
        "meta": _security_meta(event_type),
        "source": "load_test",
    }


def build_event(
    *,
    target: TargetConfig,
    config: EventGeneratorConfig,
    rng: random.Random,
    session_pool: SessionPool,
    event_type: str | None = None,
    path: str | None = None,
    referrer: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    mix = _normalize_mix(config.event_mix)
    chosen_type = event_type or _weighted_choice(mix, rng=rng)
    chosen_path = path or rng.choice(config.path_pool)
    chosen_referrer = referrer if referrer is not None else rng.choice(config.referrers)
    session_id = session_pool.pick()
    if chosen_type in SECURITY_EVENT_TYPES:
        return build_security_event(
            event_type=chosen_type,
            path=chosen_path,
            session_id=session_id,
            now=now,
        )
    timestamp = (now or datetime.now(timezone.utc)).isoformat()
    return {
        "event_id": str(uuid4()),
        "ts": timestamp,
        "type": chosen_type,
        "url": f"https://{target.domain}{chosen_path}",
        "path": chosen_path,
        "referrer": chosen_referrer,
        "session_id": session_id,
        "user_id": None,
        "meta": _default_meta(chosen_type),
    }


def build_targets(raw_targets: list[dict[str, Any]]) -> list[TargetConfig]:
    targets: list[TargetConfig] = []
    for entry in raw_targets:
        if not isinstance(entry, dict):
            continue
        api_key = str(entry.get("api_key") or "").strip()
        domain = str(entry.get("domain") or "").strip()
        if not api_key or not domain:
            continue
        weight = int(entry.get("weight") or 1)
        api_secret = entry.get("api_secret")
        if isinstance(api_secret, str):
            api_secret = api_secret.strip() or None
        targets.append(TargetConfig(api_key=api_key, domain=domain, weight=weight, api_secret=api_secret))
    return targets


def choose_target(targets: list[TargetConfig], *, rng: random.Random) -> TargetConfig:
    if not targets:
        raise ValueError("No targets configured")
    weighted = [(target, target.weight) for target in targets]
    total = sum(weight for _, weight in weighted)
    pick = rng.uniform(0, total)
    cursor = 0
    for target, weight in weighted:
        cursor += weight
        if pick <= cursor:
            return target
    return weighted[-1][0]
