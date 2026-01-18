from sqlalchemy.orm import Session

from app.models.project_tags import ProjectTag, WebsiteTag
from app.models.websites import Website


def get_tag(db: Session, tenant_id: int, tag_id: int) -> ProjectTag | None:
    return (
        db.query(ProjectTag)
        .filter(ProjectTag.tenant_id == tenant_id, ProjectTag.id == tag_id)
        .first()
    )


def create_tag(db: Session, tenant_id: int, name: str, color: str | None = None) -> ProjectTag:
    existing = (
        db.query(ProjectTag)
        .filter(ProjectTag.tenant_id == tenant_id, ProjectTag.name == name)
        .first()
    )
    if existing:
        raise ValueError("Tag already exists for tenant.")
    tag = ProjectTag(tenant_id=tenant_id, name=name, color=color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def list_tags(db: Session, tenant_id: int) -> list[ProjectTag]:
    return (
        db.query(ProjectTag)
        .filter(ProjectTag.tenant_id == tenant_id)
        .order_by(ProjectTag.name.asc())
        .all()
    )


def delete_tag(db: Session, tenant_id: int, tag_id: int) -> bool:
    tag = get_tag(db, tenant_id, tag_id)
    if not tag:
        return False
    db.query(WebsiteTag).filter(WebsiteTag.tag_id == tag_id).delete(synchronize_session=False)
    db.delete(tag)
    db.commit()
    return True


def attach_tag_to_website(
    db: Session,
    tenant_id: int,
    website_id: int,
    tag_id: int,
) -> WebsiteTag:
    website = (
        db.query(Website)
        .filter(
            Website.tenant_id == tenant_id,
            Website.id == website_id,
            Website.deleted_at.is_(None),
        )
        .first()
    )
    if not website:
        raise LookupError("Website not found")
    tag = get_tag(db, tenant_id, tag_id)
    if not tag:
        raise LookupError("Tag not found")
    existing = (
        db.query(WebsiteTag)
        .filter(WebsiteTag.website_id == website_id, WebsiteTag.tag_id == tag_id)
        .first()
    )
    if existing:
        raise ValueError("Tag already attached to website.")
    link = WebsiteTag(website_id=website_id, tag_id=tag_id)
    db.add(link)
    db.commit()
    return link


def detach_tag_from_website(
    db: Session,
    tenant_id: int,
    website_id: int,
    tag_id: int,
) -> bool:
    website = (
        db.query(Website)
        .filter(
            Website.tenant_id == tenant_id,
            Website.id == website_id,
            Website.deleted_at.is_(None),
        )
        .first()
    )
    if not website:
        return False
    tag = get_tag(db, tenant_id, tag_id)
    if not tag:
        return False
    link = (
        db.query(WebsiteTag)
        .filter(WebsiteTag.website_id == website_id, WebsiteTag.tag_id == tag_id)
        .first()
    )
    if not link:
        return False
    db.delete(link)
    db.commit()
    return True
