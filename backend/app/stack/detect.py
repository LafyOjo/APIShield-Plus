from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.stack.constants import STACK_HINT_KEYS, STACK_TYPES


@dataclass
class StackDetectionResult:
    stack_type: str
    confidence: float
    signals: dict[str, Any]


_HINT_SCORES = {
    "nextjs_detected": ("nextjs", 0.9),
    "shopify_detected": ("shopify", 0.9),
    "wordpress_detected": ("wordpress", 0.85),
    "react_spa_detected": ("react_spa", 0.65),
    "laravel_detected": ("laravel", 0.65),
    "django_detected": ("django", 0.65),
    "rails_detected": ("rails", 0.65),
    "custom_detected": ("custom", 0.4),
}


def normalize_hints(hints: dict[str, Any] | None) -> dict[str, bool]:
    if not hints or not isinstance(hints, dict):
        return {}
    normalized: dict[str, bool] = {}
    for key, value in hints.items():
        if key not in STACK_HINT_KEYS:
            continue
        if isinstance(value, bool):
            normalized[key] = value
        else:
            normalized[key] = bool(value)
    return normalized


def detect_stack_from_hints(hints: dict[str, Any] | None) -> StackDetectionResult:
    normalized = normalize_hints(hints)
    best_type = "custom"
    best_score = 0.2
    for hint_key, enabled in normalized.items():
        if not enabled:
            continue
        stack_type, score = _HINT_SCORES.get(hint_key, ("custom", 0.2))
        if score > best_score:
            best_type = stack_type
            best_score = score
    if best_type not in STACK_TYPES:
        best_type = "custom"
        best_score = 0.2
    signals = {
        "hints": normalized,
        "suggested_stack": best_type,
        "confidence": best_score,
    }
    return StackDetectionResult(stack_type=best_type, confidence=best_score, signals=signals)
