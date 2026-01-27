from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Iterable

from pydantic import BaseModel, Field


class FactorType(str, Enum):
    LOGIN_FAIL_SPIKE = "login_fail_spike"
    CREDENTIAL_STUFFING_DETECTED = "credential_stuffing_detected"
    CSP_VIOLATION_SPIKE = "csp_violation_spike"
    SCRIPT_INJECTION_SIGNAL = "script_injection_signal"
    JS_ERROR_SPIKE = "js_error_spike"
    FORM_SUBMIT_FAIL_SPIKE = "form_submit_fail_spike"
    DATACENTER_ASN_SURGE = "datacenter_asn_surge"
    GEO_NOVELTY_LOGIN = "geo_novelty_login"
    CONVERSION_DROP_OVERLAP = "conversion_drop_overlap"


class FactorSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_MULTIPLIER = {
    FactorSeverity.LOW: 0.5,
    FactorSeverity.MEDIUM: 1.0,
    FactorSeverity.HIGH: 1.5,
    FactorSeverity.CRITICAL: 2.0,
}


@dataclass(frozen=True)
class FactorDefinition:
    base_penalty: float
    decay_half_life_hours: float


FACTOR_DEFINITIONS: dict[FactorType, FactorDefinition] = {
    FactorType.LOGIN_FAIL_SPIKE: FactorDefinition(base_penalty=10.0, decay_half_life_hours=6.0),
    FactorType.CREDENTIAL_STUFFING_DETECTED: FactorDefinition(base_penalty=25.0, decay_half_life_hours=12.0),
    FactorType.CSP_VIOLATION_SPIKE: FactorDefinition(base_penalty=12.0, decay_half_life_hours=8.0),
    FactorType.SCRIPT_INJECTION_SIGNAL: FactorDefinition(base_penalty=30.0, decay_half_life_hours=24.0),
    FactorType.JS_ERROR_SPIKE: FactorDefinition(base_penalty=8.0, decay_half_life_hours=4.0),
    FactorType.FORM_SUBMIT_FAIL_SPIKE: FactorDefinition(base_penalty=10.0, decay_half_life_hours=4.0),
    FactorType.DATACENTER_ASN_SURGE: FactorDefinition(base_penalty=12.0, decay_half_life_hours=6.0),
    FactorType.GEO_NOVELTY_LOGIN: FactorDefinition(base_penalty=15.0, decay_half_life_hours=12.0),
    FactorType.CONVERSION_DROP_OVERLAP: FactorDefinition(base_penalty=10.0, decay_half_life_hours=6.0),
}

DEFAULT_FACTOR_DEFINITION = FactorDefinition(base_penalty=8.0, decay_half_life_hours=6.0)


class RiskFactor(BaseModel):
    factor_type: FactorType
    severity: FactorSeverity = FactorSeverity.MEDIUM
    observed_at: datetime
    last_seen_at: datetime | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class TrustFactor(BaseModel):
    factor_type: FactorType
    severity: FactorSeverity
    penalty: float
    decay_factor: float
    age_hours: float
    evidence: dict[str, Any]


class TrustScore(BaseModel):
    score: int
    factors: list[TrustFactor]
    window_start: datetime
    window_end: datetime
    confidence: float


class PageTrustSnapshot(BaseModel):
    page_path: str
    trust_score: TrustScore


def _hours_between(a: datetime, b: datetime) -> float:
    delta = b - a
    return max(0.0, delta.total_seconds() / 3600.0)


def _decay_factor(age_hours: float, half_life_hours: float) -> float:
    if half_life_hours <= 0:
        return 1.0
    return 0.5 ** (age_hours / half_life_hours)


def _resolve_factor_definition(factor_type: FactorType) -> FactorDefinition:
    return FACTOR_DEFINITIONS.get(factor_type, DEFAULT_FACTOR_DEFINITION)


def compute_trust_score(
    factors: Iterable[RiskFactor],
    *,
    window_start: datetime,
    window_end: datetime,
) -> TrustScore:
    contributions: list[TrustFactor] = []
    total_penalty = 0.0

    for factor in factors:
        definition = _resolve_factor_definition(factor.factor_type)
        multiplier = SEVERITY_MULTIPLIER.get(factor.severity, 1.0)
        last_seen = factor.last_seen_at or factor.observed_at
        age_hours = _hours_between(last_seen, window_end)
        decay = _decay_factor(age_hours, definition.decay_half_life_hours)
        penalty = definition.base_penalty * multiplier * decay
        total_penalty += penalty
        contributions.append(
            TrustFactor(
                factor_type=factor.factor_type,
                severity=factor.severity,
                penalty=round(penalty, 2),
                decay_factor=round(decay, 3),
                age_hours=round(age_hours, 2),
                evidence=factor.evidence,
            )
        )

    score = max(0, min(100, int(round(100 - total_penalty))))
    factor_count = len(contributions)
    confidence = 0.6 + min(0.4, factor_count * 0.1)
    confidence = round(confidence, 2)

    return TrustScore(
        score=score,
        factors=contributions,
        window_start=window_start,
        window_end=window_end,
        confidence=confidence,
    )
