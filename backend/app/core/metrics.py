# Centralized Prometheus metrics + a tiny in-memory counter
# for per-user API call totals. Middleware below records timing
# and counts for every request so dashboards can track health.

from time import monotonic
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Histogram
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

        # Record latency and increment the labeled request counter.
        REQUEST_LATENCY.labels(request.method, request.url.path).observe(duration)
        REQUEST_COUNT.labels(request.method, request.url.path, response.status_code).inc()

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
