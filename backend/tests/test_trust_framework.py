from datetime import datetime, timedelta

from app.trust.framework import (
    FactorSeverity,
    FactorType,
    RiskFactor,
    compute_trust_score,
)


def test_trust_score_decreases_with_high_severity_threat_factor():
    window_start = datetime.utcnow() - timedelta(hours=1)
    window_end = datetime.utcnow()
    factors = [
        RiskFactor(
            factor_type=FactorType.CREDENTIAL_STUFFING_DETECTED,
            severity=FactorSeverity.CRITICAL,
            observed_at=window_end,
            evidence={"count": 120},
        )
    ]
    score = compute_trust_score(factors, window_start=window_start, window_end=window_end)
    assert score.score < 100
    assert score.score <= 50
    assert score.factors
    assert score.factors[0].factor_type == FactorType.CREDENTIAL_STUFFING_DETECTED


def test_trust_score_decay_recovers_over_time_without_signals():
    now = datetime.utcnow()
    window_start = now - timedelta(hours=1)
    window_end = now

    fresh_factor = RiskFactor(
        factor_type=FactorType.JS_ERROR_SPIKE,
        severity=FactorSeverity.HIGH,
        observed_at=window_end,
        evidence={"count": 50},
    )
    fresh_score = compute_trust_score(
        [fresh_factor],
        window_start=window_start,
        window_end=window_end,
    )

    stale_factor = RiskFactor(
        factor_type=FactorType.JS_ERROR_SPIKE,
        severity=FactorSeverity.HIGH,
        observed_at=window_end - timedelta(hours=12),
        last_seen_at=window_end - timedelta(hours=12),
        evidence={"count": 50},
    )
    recovered_score = compute_trust_score(
        [stale_factor],
        window_start=window_start,
        window_end=window_end,
    )

    assert recovered_score.score > fresh_score.score


def test_trust_score_contains_explainable_factors():
    window_start = datetime.utcnow() - timedelta(hours=2)
    window_end = datetime.utcnow()
    factors = [
        RiskFactor(
            factor_type=FactorType.CSP_VIOLATION_SPIKE,
            severity=FactorSeverity.MEDIUM,
            observed_at=window_end,
            evidence={"violations": 12, "path": "/checkout"},
        )
    ]
    score = compute_trust_score(factors, window_start=window_start, window_end=window_end)
    assert score.factors
    factor = score.factors[0]
    assert factor.evidence.get("violations") == 12
    assert score.window_start == window_start
    assert score.window_end == window_end
