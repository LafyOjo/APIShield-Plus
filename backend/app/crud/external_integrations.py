from sqlalchemy.orm import Session

from app.core.crypto import encrypt_json
from app.core.integrations import validate_integration_status, validate_integration_type
from app.models.external_integrations import ExternalIntegration


def create_integration(
    db: Session,
    tenant_id: int,
    integration_type: str,
    config: dict,
    status: str = "active",
) -> ExternalIntegration:
    validate_integration_type(integration_type)
    validate_integration_status(status)
    encrypted = encrypt_json(config)
    integration = ExternalIntegration(
        tenant_id=tenant_id,
        type=integration_type,
        config_encrypted=encrypted,
        status=status,
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration


def list_integrations(db: Session, tenant_id: int) -> list[ExternalIntegration]:
    return (
        db.query(ExternalIntegration)
        .filter(ExternalIntegration.tenant_id == tenant_id)
        .order_by(ExternalIntegration.id.desc())
        .all()
    )


def get_integration(db: Session, tenant_id: int, integration_id: int) -> ExternalIntegration | None:
    return (
        db.query(ExternalIntegration)
        .filter(
            ExternalIntegration.tenant_id == tenant_id,
            ExternalIntegration.id == integration_id,
        )
        .first()
    )


def update_integration(
    db: Session,
    tenant_id: int,
    integration_id: int,
    *,
    config: dict | None = None,
    status: str | None = None,
) -> ExternalIntegration | None:
    integration = get_integration(db, tenant_id, integration_id)
    if not integration:
        return None
    if config is not None:
        integration.config_encrypted = encrypt_json(config)
    if status is not None:
        validate_integration_status(status)
        integration.status = status
    db.commit()
    db.refresh(integration)
    return integration
