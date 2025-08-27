# This uses a lightweight ML model to score incoming requests based on a
# simple feature (path length). If the score looks outlier-ish, we block it.
# It’s demo-friendly and optional: if sklearn/numpy aren’t installed, it’s a no-op.

from typing import Any
import os
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.status import HTTP_403_FORBIDDEN

# Try to import sklearn + numpy; fall back gracefully if unavailable.
# This keeps deployments flexible and lets tests run without heavy deps.
try:
    from sklearn.ensemble import IsolationForest
    from sklearn.neighbors import LocalOutlierFactor
    import numpy as np
except Exception:  # pragma: no cover - library may not be installed for tests
    IsolationForest = None  # type: ignore
    LocalOutlierFactor = None  # type: ignore
    np = None  # type: ignore


class _Model:
    # Simple wrapper around an outlier model so we can swap algorithms.
    # Trains once on synthetic “normal” data and exposes a score method.
    def __init__(self, algo: str) -> None:
        # Create a small synthetic dataset representing normal path sizes.
        # Deterministic RNG makes behavior repeatable across runs.
        rng = np.random.default_rng(42)
        X = rng.uniform(low=[1], high=[20], size=(100, 1))

        # Pick LOF or IsolationForest. LOF needs novelty=True for predict().
        # Both are set with small contamination to be “mildly suspicious,” not harsh.
        if algo == "lof" and LocalOutlierFactor is not None:
            self.model = LocalOutlierFactor(novelty=True, contamination=0.05)
            self.model.fit(X)
        else:
            self.model = IsolationForest(contamination=0.05, random_state=42)
            self.model.fit(X)

    # Return -1 for outlier, 1 for inlier. Keep as an int for easy checks.
    # Wrap predict() so callers don’t need to know sklearn’s API details.
    def score(self, value: float) -> int:
        return int(self.model.predict([[value]])[0])


# Cache the model so we don’t retrain for every request.
# Starts as None; get_model() lazily builds it when needed.
_model: Any = None


def get_model() -> _Model | None:
    # Lazily instantiate based on env var; default to IsolationForest.
    # If sklearn isn’t available, stick with None so middleware no-ops.
    global _model
    if _model is None and IsolationForest is not None:
        algo = os.getenv("ANOMALY_MODEL", "isolation_forest").lower()
        _model = _Model(algo)
    return _model


class AnomalyDetectionMiddleware(BaseHTTPMiddleware):
    # Middleware runs on every request. If ML libs aren’t present, bail fast.
    # Otherwise, score the path length and block obvious outliers with 403.
    async def dispatch(self, request: Request, call_next):
        if IsolationForest is None or np is None:
            return await call_next(request)

        model = get_model()
        if model is None:
            return await call_next(request)

        # Use a super simple feature: path length. It’s cheap and deterministic.
        # In real apps you’d use richer features (method, headers, rates, etc.).
        path_len = len(request.url.path)

        # If the model flags it as an outlier (-1), return a quick 403 JSON.
        # Otherwise, allow the request to proceed normally down the stack.
        if model.score(path_len) == -1:
            return JSONResponse({"detail": "Anomalous request"}, status_code=HTTP_403_FORBIDDEN)
        return await call_next(request)
