from datetime import datetime, timedelta
import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")

from app.entitlements.enforcement import (
    FeatureNotEnabled,
    PlanLimitExceeded,
    assert_limit,
    clamp_range,
    require_feature,
)


def test_require_feature_blocks_when_disabled():
    entitlements = {"features": {"geo_map": False}, "plan_key": "free"}
    with pytest.raises(FeatureNotEnabled) as exc:
        require_feature(entitlements, "geo_map")
    assert exc.value.code == "feature_not_enabled"
    assert exc.value.status_code == 403


def test_assert_limit_blocks_when_exceeded_in_hard_cap_mode():
    entitlements = {"limits": {"websites": 1}, "plan_key": "free"}
    with pytest.raises(PlanLimitExceeded) as exc:
        assert_limit(entitlements, "websites", 1, mode="hard")
    assert exc.value.code == "plan_limit_exceeded"
    assert exc.value.status_code == 402


def test_clamp_range_reduces_requested_window_to_limit():
    now = datetime(2026, 1, 10, 12, 0, 0)
    from_ts = now - timedelta(days=7)
    to_ts = now - timedelta(hours=1)
    entitlements = {"limits": {"geo_history_days": 1}}

    result = clamp_range(entitlements, "geo_history_days", from_ts, to_ts, now=now)

    assert result.clamped is True
    assert result.max_days == 1
    assert result.from_ts == now - timedelta(days=1)
    assert result.to_ts == to_ts
