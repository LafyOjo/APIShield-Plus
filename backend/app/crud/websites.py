from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.entitlements import assert_can_create_website
from app.core.utils.domain import normalize_domain
from app.models.enums import WebsiteStatusEnum
from app.models.websites import Website
from app.models.website_environments import WebsiteEnvironment
from app.tenancy.errors import TenantNotFound
from app.tenancy.scoping import scoped_query


def _normalize_status(status: WebsiteStatusEnum | str) -> WebsiteStatusEnum:
    if isinstance(status, WebsiteStatusEnum):
        return status
    try:
        return WebsiteStatusEnum(status)
    except ValueError as exc:
        raise ValueError("Invalid website status.") from exc


def create_website(
    db: Session,
    tenant_id: int,
    domain: str,
    display_name: str | None = None,
    created_by_user_id: int | None = None,
) -> Website:
    assert_can_create_website(tenant_id)
    normalized = normalize_domain(domain)
    existing = scoped_query(db, Website, tenant_id).filter(Website.domain == normalized).first()
    if existing:
        raise ValueError("Website already exists for tenant.")
    website = Website(
        tenant_id=tenant_id,
        domain=normalized,
        display_name=display_name,
        created_by_user_id=created_by_user_id,
        status=WebsiteStatusEnum.ACTIVE,
    )
    db.add(website)
    db.flush()
    db.add(WebsiteEnvironment(website_id=website.id, name="production", status="active"))
    try:
        db.commit()
        db.refresh(website)
        return website
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Website already exists for tenant.") from exc


def _website_query(db: Session, tenant_id: int, *, include_deleted: bool = False):
    query = scoped_query(db, Website, tenant_id)
    if not include_deleted:
        query = query.filter(
            Website.status != WebsiteStatusEnum.DELETED,
            Website.deleted_at.is_(None),
        )
    return query


def list_websites(
    db: Session,
    tenant_id: int,
    *,
    include_deleted: bool = False,
) -> list[Website]:
    return _website_query(db, tenant_id, include_deleted=include_deleted).order_by(Website.id).all()


def get_website(
    db: Session,
    tenant_id: int,
    website_id: int,
    *,
    include_deleted: bool = False,
) -> Website:
    website = (
        _website_query(db, tenant_id, include_deleted=include_deleted)
        .filter(Website.id == website_id)
        .first()
    )
    if not website:
        raise TenantNotFound("Website not found for tenant")
    return website


def get_website_by_domain(
    db: Session,
    tenant_id: int,
    domain: str,
    *,
    include_deleted: bool = False,
) -> Website:
    normalized = normalize_domain(domain)
    website = (
        _website_query(db, tenant_id, include_deleted=include_deleted)
        .filter(Website.domain == normalized)
        .first()
    )
    if not website:
        raise TenantNotFound("Website not found for tenant")
    return website


def update_website(
    db: Session,
    tenant_id: int,
    website_id: int,
    *,
    display_name: str | None = None,
    status: WebsiteStatusEnum | str | None = None,
) -> Website:
    website = get_website(db, tenant_id, website_id)
    if display_name is not None:
        website.display_name = display_name
    if status is not None:
        normalized_status = _normalize_status(status)
        website.status = normalized_status
        if normalized_status == WebsiteStatusEnum.DELETED and website.deleted_at is None:
            website.deleted_at = datetime.now(timezone.utc)
        elif normalized_status != WebsiteStatusEnum.DELETED and website.deleted_at is not None:
            website.deleted_at = None
    db.commit()
    db.refresh(website)
    return website


def soft_delete_website(db: Session, tenant_id: int, website_id: int) -> Website:
    website = get_website(db, tenant_id, website_id)
    website.status = WebsiteStatusEnum.DELETED
    website.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(website)
    return website


def pause_website(db: Session, tenant_id: int, website_id: int) -> Website:
    website = get_website(db, tenant_id, website_id)
    website.status = WebsiteStatusEnum.PAUSED
    db.commit()
    db.refresh(website)
    return website


def resume_website(db: Session, tenant_id: int, website_id: int) -> Website:
    website = get_website(db, tenant_id, website_id)
    website.status = WebsiteStatusEnum.ACTIVE
    db.commit()
    db.refresh(website)
    return website


def restore_website(db: Session, tenant_id: int, website_id: int) -> Website:
    website = get_website(db, tenant_id, website_id, include_deleted=True)
    if website.deleted_at is None:
        return website
    website.deleted_at = None
    if website.status == WebsiteStatusEnum.DELETED:
        website.status = WebsiteStatusEnum.ACTIVE
    db.commit()
    db.refresh(website)
    return website
