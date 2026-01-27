from __future__ import annotations


ALLOWED_EXPORT_TARGETS = {"local", "s3", "gcs", "azure_blob"}
ALLOWED_EXPORT_FORMATS = {"jsonl.gz", "csv.gz"}
ALLOWED_EXPORT_DATASETS = {
    "incidents",
    "security_events",
    "geo_agg",
    "conversion_metrics",
    "notification_deliveries",
}
DEFAULT_EXPORT_DATASETS = [
    "incidents",
    "security_events",
    "geo_agg",
    "conversion_metrics",
    "notification_deliveries",
]


def normalize_export_schedule(value: str | None) -> str:
    if not value:
        return "daily"
    return value.strip() or "daily"


def normalize_datasets(values: list[str] | None) -> list[str]:
    if not values:
        return list(DEFAULT_EXPORT_DATASETS)
    normalized = []
    for item in values:
        if item is None:
            continue
        candidate = str(item).strip().lower()
        if not candidate:
            continue
        normalized.append(candidate)
    if not normalized:
        return list(DEFAULT_EXPORT_DATASETS)
    return normalized


def validate_export_target(value: str) -> str:
    target = (value or "").strip().lower()
    if not target:
        raise ValueError("target_type is required")
    if target not in ALLOWED_EXPORT_TARGETS:
        raise ValueError("Unsupported export target")
    return target


def validate_export_format(value: str | None) -> str:
    if not value:
        return "jsonl.gz"
    cleaned = value.strip().lower()
    if cleaned not in ALLOWED_EXPORT_FORMATS:
        raise ValueError("Unsupported export format")
    return cleaned


def validate_export_datasets(values: list[str]) -> list[str]:
    invalid = [item for item in values if item not in ALLOWED_EXPORT_DATASETS]
    if invalid:
        raise ValueError(f"Unsupported datasets: {', '.join(invalid)}")
    return values
