from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.verification import generate_verification_token, validate_verification_method
from app.models.domain_verification import DomainVerification


def create_verification(
    db: Session,
    tenant_id: int,
    website_id: int,
    method: str,
    created_by_user_id: int | None = None,
) -> DomainVerification:
    validate_verification_method(method)
    for _ in range(5):
        token = generate_verification_token()
        verification = DomainVerification(
            tenant_id=tenant_id,
            website_id=website_id,
            method=method,
            token=token,
            status="pending",
            created_by_user_id=created_by_user_id,
        )
        db.add(verification)
        try:
            db.commit()
            db.refresh(verification)
            return verification
        except IntegrityError:
            db.rollback()
            db.expunge(verification)
    raise RuntimeError("Unable to generate a unique verification token")


def get_latest_verification(
    db: Session,
    tenant_id: int,
    website_id: int,
    method: str | None = None,
) -> DomainVerification | None:
    query = (
        db.query(DomainVerification)
        .filter(
            DomainVerification.tenant_id == tenant_id,
            DomainVerification.website_id == website_id,
        )
        .order_by(DomainVerification.created_at.desc())
    )
    if method:
        validate_verification_method(method)
        query = query.filter(DomainVerification.method == method)
    return query.first()


def update_check_status(
    db: Session,
    verification: DomainVerification,
    *,
    verified: bool | None = None,
) -> DomainVerification:
    verification.last_checked_at = datetime.now(timezone.utc)
    if verified is True:
        verification.status = "verified"
        verification.verified_at = datetime.now(timezone.utc)
    elif verified is False:
        verification.status = "failed"
    db.commit()
    db.refresh(verification)
    return verification
