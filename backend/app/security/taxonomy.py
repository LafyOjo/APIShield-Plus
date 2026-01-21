from __future__ import annotations

from enum import Enum


class SecurityCategoryEnum(str, Enum):
    LOGIN = "login"
    THREAT = "threat"
    INTEGRITY = "integrity"
    BOT = "bot"
    ANOMALY = "anomaly"


class SeverityEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityEventTypeEnum(str, Enum):
    LOGIN_ATTEMPT = "login_attempt"
    LOGIN_ATTEMPT_FAILED = "login_attempt_failed"
    LOGIN_ATTEMPT_SUCCEEDED = "login_attempt_succeeded"
    BRUTE_FORCE = "brute_force"
    CREDENTIAL_STUFFING = "credential_stuffing"
    CREDENTIAL_STUFFING_BLOCKED = "credential_stuffing_blocked"
    SQL_INJECTION_ATTEMPT = "sql_injection_attempt"
    XSS_ATTEMPT = "xss_attempt"
    SCRIPT_INJECTION_DETECTED = "script_injection_detected"
    CSP_VIOLATION = "csp_violation"
    FORM_TAMPER = "form_tamper"
    BOT_SURGE = "bot_surge"
    HEADLESS_BROWSER_DETECTED = "headless_browser_detected"
    RATE_LIMIT_TRIGGERED = "rate_limit_triggered"
    ANOMALOUS_REQUEST = "anomalous_request"
    JS_ERROR_EVENT = "js_error_event"


SECURITY_EVENT_TYPE_TO_CATEGORY = {
    SecurityEventTypeEnum.LOGIN_ATTEMPT: SecurityCategoryEnum.LOGIN,
    SecurityEventTypeEnum.LOGIN_ATTEMPT_FAILED: SecurityCategoryEnum.LOGIN,
    SecurityEventTypeEnum.LOGIN_ATTEMPT_SUCCEEDED: SecurityCategoryEnum.LOGIN,
    SecurityEventTypeEnum.BRUTE_FORCE: SecurityCategoryEnum.THREAT,
    SecurityEventTypeEnum.CREDENTIAL_STUFFING: SecurityCategoryEnum.THREAT,
    SecurityEventTypeEnum.CREDENTIAL_STUFFING_BLOCKED: SecurityCategoryEnum.THREAT,
    SecurityEventTypeEnum.SQL_INJECTION_ATTEMPT: SecurityCategoryEnum.THREAT,
    SecurityEventTypeEnum.XSS_ATTEMPT: SecurityCategoryEnum.THREAT,
    SecurityEventTypeEnum.SCRIPT_INJECTION_DETECTED: SecurityCategoryEnum.THREAT,
    SecurityEventTypeEnum.CSP_VIOLATION: SecurityCategoryEnum.INTEGRITY,
    SecurityEventTypeEnum.FORM_TAMPER: SecurityCategoryEnum.INTEGRITY,
    SecurityEventTypeEnum.BOT_SURGE: SecurityCategoryEnum.BOT,
    SecurityEventTypeEnum.HEADLESS_BROWSER_DETECTED: SecurityCategoryEnum.BOT,
    SecurityEventTypeEnum.RATE_LIMIT_TRIGGERED: SecurityCategoryEnum.BOT,
    SecurityEventTypeEnum.ANOMALOUS_REQUEST: SecurityCategoryEnum.ANOMALY,
    SecurityEventTypeEnum.JS_ERROR_EVENT: SecurityCategoryEnum.ANOMALY,
}

SECURITY_EVENT_TYPE_TO_SEVERITY = {
    SecurityEventTypeEnum.LOGIN_ATTEMPT: SeverityEnum.LOW,
    SecurityEventTypeEnum.LOGIN_ATTEMPT_FAILED: SeverityEnum.MEDIUM,
    SecurityEventTypeEnum.LOGIN_ATTEMPT_SUCCEEDED: SeverityEnum.LOW,
    SecurityEventTypeEnum.BRUTE_FORCE: SeverityEnum.HIGH,
    SecurityEventTypeEnum.CREDENTIAL_STUFFING: SeverityEnum.HIGH,
    SecurityEventTypeEnum.CREDENTIAL_STUFFING_BLOCKED: SeverityEnum.HIGH,
    SecurityEventTypeEnum.SQL_INJECTION_ATTEMPT: SeverityEnum.HIGH,
    SecurityEventTypeEnum.XSS_ATTEMPT: SeverityEnum.HIGH,
    SecurityEventTypeEnum.SCRIPT_INJECTION_DETECTED: SeverityEnum.HIGH,
    SecurityEventTypeEnum.CSP_VIOLATION: SeverityEnum.MEDIUM,
    SecurityEventTypeEnum.FORM_TAMPER: SeverityEnum.MEDIUM,
    SecurityEventTypeEnum.BOT_SURGE: SeverityEnum.MEDIUM,
    SecurityEventTypeEnum.HEADLESS_BROWSER_DETECTED: SeverityEnum.MEDIUM,
    SecurityEventTypeEnum.RATE_LIMIT_TRIGGERED: SeverityEnum.MEDIUM,
    SecurityEventTypeEnum.ANOMALOUS_REQUEST: SeverityEnum.MEDIUM,
    SecurityEventTypeEnum.JS_ERROR_EVENT: SeverityEnum.LOW,
}


def normalize_event_type(value: SecurityEventTypeEnum | str) -> SecurityEventTypeEnum:
    if isinstance(value, SecurityEventTypeEnum):
        return value
    normalized = str(value).strip().lower()
    try:
        return SecurityEventTypeEnum(normalized)
    except ValueError as exc:
        raise ValueError(f"Unsupported security event type: {value}") from exc


def validate_event_type(value: SecurityEventTypeEnum | str) -> None:
    normalize_event_type(value)


def get_category(event_type: SecurityEventTypeEnum | str) -> SecurityCategoryEnum:
    normalized = normalize_event_type(event_type)
    category = SECURITY_EVENT_TYPE_TO_CATEGORY.get(normalized)
    if not category:
        raise ValueError(f"No category mapping for event type: {event_type}")
    return category


def get_severity(event_type: SecurityEventTypeEnum | str) -> SeverityEnum:
    normalized = normalize_event_type(event_type)
    severity = SECURITY_EVENT_TYPE_TO_SEVERITY.get(normalized)
    if not severity:
        raise ValueError(f"No severity mapping for event type: {event_type}")
    return severity
