import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.tenants import Tenant


def slugify(name: str) -> str:
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "tenant"


def ensure_unique_slug(db: Session, base_slug: str, *, exclude_id: Optional[int] = None) -> str:
    slug = base_slug
    suffix = 2
    while True:
        query = db.query(Tenant).filter(Tenant.slug == slug)
        if exclude_id is not None:
            query = query.filter(Tenant.id != exclude_id)
        if query.first() is None:
            return slug
        slug = f"{base_slug}-{suffix}"
        suffix += 1
