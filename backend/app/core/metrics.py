# Centralized Prometheus metrics + a tiny in-memory counter
# for per-user API call totals. Middleware below records timing
# and counts for every request so dashboards can track health.

from time import monotonic
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Histogram, Gauge
from collections import defaultdict
from app.core.security import decode_access_token

# Login attempts metric with labels for username + outcome.
# This lets us graph successes vs failures and catch spikes.
# Usernames are normalized elsewhere to keep series stable.
login_attempts_total = Counter(
    "login_attempts_total",
    "Login attempts grouped by outcome and user",
    ["username", "outcome"],   # outcome: success|fail
)

# Credential stuffing counter keyed by username. Useful to show
# which accounts are being hammered and how often we detect it.
credential_stuffing_attempts_total = Counter(
    "credential_stuffing_attempts_total",
    "Detected credential stuffing attempts",
    ["username"],
)

# When a policy/rule blocks something, we record the rule name,
# user, and IP. This helps debug which protections are firing.
events_blocked_total = Counter(
    "events_blocked_total",
    "Security events blocked by policy/rule",
    ["rule", "username", "ip"],
)

# End-to-end login latency histogram. Explains auth slowness and
# helps spot regressions. Bucket sizes cover common web latencies.
login_request_duration_seconds = Histogram(
    "login_request_duration_seconds",
    "Login request duration",
    buckets=[0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10],
)

# Generic API latency + request counters. We label by method and
# endpoint so we can see hot paths and slow ones at a glance.
REQUEST_LATENCY = Histogram(
    "api_request_latency_seconds",
    "Latency of API requests in seconds",
    ["method", "endpoint"],
)
REQUEST_COUNT = Counter(
    "api_request_count_total",
    "Total API requests",
    ["method", "endpoint", "http_status"],
)

REQUEST_DURATION_MS = Histogram(
    "request_duration_ms",
    "API request duration in milliseconds",
    ["method", "route"],
    buckets=[5, 10, 25, 50, 100, 250, 500, 1000, 2000, 5000, 10000],
)
REQUESTS_TOTAL = Counter(
    "requests_total",
    "Total API requests",
    ["method", "route", "status_code"],
)

INGEST_EVENTS_TOTAL = Counter(
    "ingest_events_total",
    "Total ingested events",
    ["tenant_id", "website_id", "environment_id", "event_type", "ingest_type"],
)
INGEST_LATENCY_MS = Histogram(
    "ingest_latency_ms",
    "Ingest request latency in milliseconds",
    ["ingest_type"],
    buckets=[5, 10, 25, 50, 100, 250, 500, 1000, 2000, 5000, 10000],
)

NOTIFICATIONS_SENT_TOTAL = Counter(
    "notifications_sent_total",
    "Notifications sent successfully",
    ["channel_type", "trigger_type"],
)
NOTIFICATIONS_FAILED_TOTAL = Counter(
    "notifications_failed_total",
    "Notifications that failed to send",
    ["channel_type", "trigger_type"],
)

CACHE_HIT_TOTAL = Counter(
    "cache_hit_total",
    "Cache hits by cache name",
    ["cache"],
)
CACHE_MISS_TOTAL = Counter(
    "cache_miss_total",
    "Cache misses by cache name",
    ["cache"],
)
CACHE_SET_TOTAL = Counter(
    "cache_set_total",
    "Cache sets by cache name",
    ["cache"],
)
CACHE_PAYLOAD_BYTES = Histogram(
    "cache_payload_bytes",
    "Cached payload size in bytes",
    ["cache"],
    buckets=[100, 500, 1000, 5000, 10000, 50000, 100000, 500000, 1000000, 5000000],
)

JOB_RUN_TOTAL = Counter(
    "job_run_total",
    "Background job runs",
    ["job_name", "status"],
)

QUEUE_DEPTH = Gauge(
    "queue_depth",
    "Queued jobs by queue",
    ["queue"],
)
QUEUE_JOB_TOTAL = Counter(
    "queue_job_total",
    "Queue jobs processed",
    ["queue", "job_type", "status"],
)
QUEUE_RETRY_TOTAL = Counter(
    "queue_retry_total",
    "Queue jobs retried",
    ["queue", "job_type"],
)
QUEUE_WAIT_SECONDS = Histogram(
    "queue_wait_seconds",
    "Time a job spent waiting in queue",
    ["queue", "job_type"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600],
)
QUEUE_RUN_SECONDS = Histogram(
    "queue_run_seconds",
    "Queue job runtime in seconds",
    ["queue", "job_type"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60],
)

SLOW_QUERY_TOTAL = Counter(
    "slow_query_total",
    "Slow query count",
    ["route", "method"],
)

# Per-user API call totals. Prometheus gives us timeseries, and
# the dict below serves the /api/user-calls endpoint for the UI.
USER_REQUEST_COUNT = Counter(
    "api_user_request_total",
    "Total API requests per user",
    ["user"],
)

# In-memory aggregate of per-user counts for quick JSON returns.
# defaultdict keeps the increment code short and free of checks.
_user_counts: defaultdict[str, int] = defaultdict(int)


def increment_user(user: str) -> None:
    # Bump both the Prometheus series and the in-memory map. Keeping
    # them in sync means we get live graphs and a fast API response.
    USER_REQUEST_COUNT.labels(user=user).inc()
    _user_counts[user] += 1


def get_user_counts() -> dict[str, int]:
    # Expose a plain dict for JSON serialization. The endpoint
    # that calls this is admin-only and read-only by design.
    return dict(_user_counts)


def record_login_attempt(username: str, success: bool) -> None:
    # Normalize the username and attach the success/fail label.
    # Small detail that pays off: consistent labels = clean charts.
    u = (username or "unknown").lower()
    login_attempts_total.labels(username=u, outcome=("success" if success else "fail")).inc()


def record_credential_stuffing(username: str) -> None:
    # Separate counter for stuffing attempts, so we can track it
    # independently from generic login failures.
    u = (username or "unknown").lower()
    credential_stuffing_attempts_total.labels(username=u).inc()


def record_block(rule: str, username: str, ip: str) -> None:
    # When a rule blocks an action, we capture which rule fired and
    # who/where it was tied to. Great for auditing and tuning rules.
    events_blocked_total.labels(
        rule=(rule or "unknown"),
        username=(username or "unknown").lower(),
        ip=(ip or "unknown"),
    ).inc()


class MetricsMiddleware(BaseHTTPMiddleware):
    # Middleware that wraps every request to capture latency, count,
    # and a best-effort username (from the bearer token if present).
    # It’s lightweight and stays out of the request’s main logic.
    async def dispatch(self, request: Request, call_next):
        # Measure start time before handing off to the route handler.
        start = monotonic()
        response = await call_next(request)
        duration = monotonic() - start
        duration_ms = duration * 1000.0

        # Record latency and increment the labeled request counter.
        route = request.scope.get("route")
        route_path = getattr(route, "path", None) or request.url.path
        REQUEST_LATENCY.labels(request.method, route_path).observe(duration)
        REQUEST_COUNT.labels(request.method, route_path, response.status_code).inc()
        REQUEST_DURATION_MS.labels(request.method, route_path).observe(duration_ms)
        REQUESTS_TOTAL.labels(request.method, route_path, str(response.status_code)).inc()

        # Best-effort attribution: decode JWT if present to tag the user.
        # If anything fails, we fall back to "unknown" to keep metrics flowing.
        user = "anonymous"
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            token = auth.split()[1]
            try:
                payload = decode_access_token(token)
                user = payload.get("sub", "unknown") or "unknown"
            except Exception:
                user = "unknown"

        # Bump per-user counters after we’ve attributed the request.
        increment_user(user)

        return response


def _label(value: object | None, default: str = "unknown") -> str:
    if value is None:
        return default
    if isinstance(value, str) and not value.strip():
        return default
    return str(value)


def record_ingest_event(
    *,
    tenant_id: int | None,
    website_id: int | None,
    environment_id: int | None,
    event_type: str | None,
    ingest_type: str,
) -> None:
    INGEST_EVENTS_TOTAL.labels(
        tenant_id=_label(tenant_id),
        website_id=_label(website_id),
        environment_id=_label(environment_id),
        event_type=_label(event_type),
        ingest_type=_label(ingest_type, "unknown"),
    ).inc()


def record_ingest_latency(*, ingest_type: str, duration_ms: float) -> None:
    INGEST_LATENCY_MS.labels(ingest_type=_label(ingest_type, "unknown")).observe(duration_ms)


def record_notification_delivery(
    *,
    channel_type: str | None,
    trigger_type: str | None,
    success: bool,
) -> None:
    labels = {
        "channel_type": _label(channel_type),
        "trigger_type": _label(trigger_type),
    }
    if success:
        NOTIFICATIONS_SENT_TOTAL.labels(**labels).inc()
    else:
        NOTIFICATIONS_FAILED_TOTAL.labels(**labels).inc()


def record_cache_hit(cache_name: str) -> None:
    CACHE_HIT_TOTAL.labels(cache=_label(cache_name, "default")).inc()


def record_cache_miss(cache_name: str) -> None:
    CACHE_MISS_TOTAL.labels(cache=_label(cache_name, "default")).inc()


def record_cache_set(cache_name: str, payload_bytes: int | None = None) -> None:
    CACHE_SET_TOTAL.labels(cache=_label(cache_name, "default")).inc()
    if payload_bytes is not None:
        CACHE_PAYLOAD_BYTES.labels(cache=_label(cache_name, "default")).observe(payload_bytes)


def record_job_run(*, job_name: str, success: bool) -> None:
    JOB_RUN_TOTAL.labels(
        job_name=_label(job_name),
        status="success" if success else "failure",
    ).inc()


def record_queue_depth(queue_name: str, depth: int) -> None:
    QUEUE_DEPTH.labels(queue=_label(queue_name)).set(depth)


def record_queue_job(queue_name: str, job_type: str, *, status: str) -> None:
    QUEUE_JOB_TOTAL.labels(
        queue=_label(queue_name),
        job_type=_label(job_type),
        status=_label(status),
    ).inc()


def record_queue_retry(queue_name: str, job_type: str) -> None:
    QUEUE_RETRY_TOTAL.labels(
        queue=_label(queue_name),
        job_type=_label(job_type),
    ).inc()


def record_queue_wait(queue_name: str, job_type: str, seconds: float) -> None:
    QUEUE_WAIT_SECONDS.labels(
        queue=_label(queue_name),
        job_type=_label(job_type),
    ).observe(seconds)


def record_queue_runtime(queue_name: str, job_type: str, seconds: float) -> None:
    QUEUE_RUN_SECONDS.labels(
        queue=_label(queue_name),
        job_type=_label(job_type),
    ).observe(seconds)


def record_slow_query(route: str | None, method: str | None) -> None:
    SLOW_QUERY_TOTAL.labels(
        route=_label(route),
        method=_label(method),
    ).inc()
