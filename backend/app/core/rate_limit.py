from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock


BUCKET_TTL_SECONDS = 600
INVALID_WINDOW_SECONDS = 60
CLEANUP_INTERVAL_SECONDS = 60


@dataclass
class TokenBucket:
    capacity: float
    tokens: float
    refill_rate: float
    updated_at: float
    last_seen: float


_BUCKETS: dict[str, TokenBucket] = {}
_INVALID_ATTEMPTS: dict[str, tuple[int, float]] = {}
_ABUSE_ATTEMPTS: dict[str, tuple[int, float]] = {}
_BANNED: dict[str, float] = {}
_LAST_CLEANUP = 0.0
_LOCK = Lock()


def _cleanup(now: float) -> None:
    global _LAST_CLEANUP
    if now - _LAST_CLEANUP < CLEANUP_INTERVAL_SECONDS:
        return
    _LAST_CLEANUP = now
    expired = [key for key, bucket in _BUCKETS.items() if now - bucket.last_seen > BUCKET_TTL_SECONDS]
    for key in expired:
        _BUCKETS.pop(key, None)
    invalid_expired = [key for key, entry in _INVALID_ATTEMPTS.items() if now - entry[1] > INVALID_WINDOW_SECONDS]
    for key in invalid_expired:
        _INVALID_ATTEMPTS.pop(key, None)
    abuse_expired = [key for key, entry in _ABUSE_ATTEMPTS.items() if now - entry[1] > INVALID_WINDOW_SECONDS]
    for key in abuse_expired:
        _ABUSE_ATTEMPTS.pop(key, None)
    banned_expired = [key for key, until in _BANNED.items() if until <= now]
    for key in banned_expired:
        _BANNED.pop(key, None)


def allow(
    key: str,
    *,
    capacity: int,
    refill_rate_per_sec: float,
) -> tuple[bool, int]:
    if capacity <= 0 or refill_rate_per_sec <= 0:
        return False, 60
    now = time.monotonic()
    with _LOCK:
        _cleanup(now)
        bucket = _BUCKETS.get(key)
        if bucket is None:
            bucket = TokenBucket(
                capacity=float(capacity),
                tokens=float(capacity),
                refill_rate=refill_rate_per_sec,
                updated_at=now,
                last_seen=now,
            )
            _BUCKETS[key] = bucket
        else:
            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(bucket.capacity, bucket.tokens + elapsed * bucket.refill_rate)
            bucket.updated_at = now
            bucket.last_seen = now

        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return True, 0
        retry_after = max(1, int((1.0 - bucket.tokens) / bucket.refill_rate))
        return False, retry_after


def is_banned(subject: str | None) -> tuple[bool, int]:
    if not subject:
        return False, 0
    now = time.monotonic()
    with _LOCK:
        _cleanup(now)
        until = _BANNED.get(subject)
        if until and until > now:
            return True, max(1, int(until - now))
        return False, 0


def register_invalid_attempt(
    subject: str | None,
    *,
    threshold: int,
    ban_seconds: int,
    window_seconds: int = INVALID_WINDOW_SECONDS,
) -> int | None:
    if not subject:
        return None
    now = time.monotonic()
    with _LOCK:
        _cleanup(now)
        count, window_start = _INVALID_ATTEMPTS.get(subject, (0, now))
        if now - window_start > window_seconds:
            count = 0
            window_start = now
        count += 1
        if count >= threshold:
            _INVALID_ATTEMPTS.pop(subject, None)
            _BANNED[subject] = now + ban_seconds
            return ban_seconds
        _INVALID_ATTEMPTS[subject] = (count, window_start)
    return None


def register_abuse_attempt(
    subject: str | None,
    *,
    threshold: int,
    ban_seconds: int,
    window_seconds: int = INVALID_WINDOW_SECONDS,
) -> int | None:
    if not subject:
        return None
    now = time.monotonic()
    with _LOCK:
        _cleanup(now)
        count, window_start = _ABUSE_ATTEMPTS.get(subject, (0, now))
        if now - window_start > window_seconds:
            count = 0
            window_start = now
        count += 1
        if count >= threshold:
            _ABUSE_ATTEMPTS.pop(subject, None)
            _BANNED[subject] = now + ban_seconds
            return ban_seconds
        _ABUSE_ATTEMPTS[subject] = (count, window_start)
    return None


def reset_state() -> None:
    with _LOCK:
        _BUCKETS.clear()
        _INVALID_ATTEMPTS.clear()
        _ABUSE_ATTEMPTS.clear()
        _BANNED.clear()
        global _LAST_CLEANUP
        _LAST_CLEANUP = 0.0
