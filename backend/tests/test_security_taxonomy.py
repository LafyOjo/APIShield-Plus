import pytest

from app.security.taxonomy import (
    SecurityCategoryEnum,
    SecurityEventTypeEnum,
    get_category,
    validate_event_type,
)


def test_security_event_type_maps_to_expected_category():
    assert get_category(SecurityEventTypeEnum.LOGIN_ATTEMPT_FAILED) == SecurityCategoryEnum.LOGIN
    assert get_category("sql_injection_attempt") == SecurityCategoryEnum.THREAT
    assert get_category("csp_violation") == SecurityCategoryEnum.INTEGRITY
    assert get_category("headless_browser_detected") == SecurityCategoryEnum.BOT
    assert get_category("anomalous_request") == SecurityCategoryEnum.ANOMALY


def test_security_event_type_allowlist_rejects_unknown():
    with pytest.raises(ValueError):
        validate_event_type("unknown_event_type")
