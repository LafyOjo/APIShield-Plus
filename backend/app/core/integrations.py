ALLOWED_INTEGRATION_TYPES = {
    "shopify",
    "wordpress",
    "cloudflare",
    "slack",
    "email_smtp",
}

ALLOWED_INTEGRATION_STATUSES = {
    "active",
    "disabled",
    "error",
}


def validate_integration_type(value: str) -> None:
    if value not in ALLOWED_INTEGRATION_TYPES:
        raise ValueError(f"Unsupported integration type: {value}")


def validate_integration_status(value: str) -> None:
    if value not in ALLOWED_INTEGRATION_STATUSES:
        raise ValueError(f"Unsupported integration status: {value}")
