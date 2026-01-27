from sqlalchemy.orm import Session

from app.core.crypto import encrypt_json
from app.core.exports import (
    normalize_datasets,
    normalize_export_schedule,
    validate_export_datasets,
    validate_export_format,
    validate_export_target,
)
from app.models.data_exports import DataExportConfig


def get_export_config(db: Session, tenant_id: int) -> DataExportConfig | None:
    return (
        db.query(DataExportConfig)
        .filter(DataExportConfig.tenant_id == tenant_id)
        .first()
    )


def upsert_export_config(
    db: Session,
    tenant_id: int,
    *,
    target_type: str,
    target_config: dict | None,
    schedule: str | None,
    datasets_enabled: list[str] | None,
    format_value: str | None,
    is_enabled: bool | None,
) -> DataExportConfig:
    normalized_target = validate_export_target(target_type)
    normalized_schedule = normalize_export_schedule(schedule)
    normalized_datasets = validate_export_datasets(normalize_datasets(datasets_enabled))
    normalized_format = validate_export_format(format_value)

    config = get_export_config(db, tenant_id)
    if not config:
        config = DataExportConfig(tenant_id=tenant_id)
        db.add(config)

    config.target_type = normalized_target
    config.schedule = normalized_schedule
    config.datasets_enabled = normalized_datasets
    config.format = normalized_format
    if is_enabled is not None:
        config.is_enabled = is_enabled

    if target_config is not None:
        if not isinstance(target_config, dict):
            raise ValueError("target_config must be a JSON object")
        config.target_secret_enc = encrypt_json(target_config)
    elif not config.target_secret_enc and normalized_target != "local":
        raise ValueError("target_config is required for non-local targets")

    db.commit()
    db.refresh(config)
    return config


def update_export_config(
    db: Session,
    tenant_id: int,
    *,
    target_type: str | None = None,
    target_config: dict | None = None,
    schedule: str | None = None,
    datasets_enabled: list[str] | None = None,
    format_value: str | None = None,
    is_enabled: bool | None = None,
) -> DataExportConfig | None:
    config = get_export_config(db, tenant_id)
    if not config:
        return None

    normalized_target = config.target_type
    if target_type is not None:
        normalized_target = validate_export_target(target_type)
        config.target_type = normalized_target

    if schedule is not None:
        config.schedule = normalize_export_schedule(schedule)
    if datasets_enabled is not None:
        normalized_datasets = validate_export_datasets(normalize_datasets(datasets_enabled))
        config.datasets_enabled = normalized_datasets
    if format_value is not None:
        config.format = validate_export_format(format_value)
    if is_enabled is not None:
        config.is_enabled = is_enabled

    if target_config is not None:
        if not isinstance(target_config, dict):
            raise ValueError("target_config must be a JSON object")
        config.target_secret_enc = encrypt_json(target_config)
    elif target_type is not None and normalized_target != "local" and not config.target_secret_enc:
        raise ValueError("target_config is required for non-local targets")

    db.commit()
    db.refresh(config)
    return config
