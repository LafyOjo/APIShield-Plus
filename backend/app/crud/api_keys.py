from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.keys import generate_public_key, generate_secret, hash_secret
from app.models.api_keys import APIKey
from app.tenancy.scoping import get_tenant_owned_or_404, scoped_query

MAX_KEY_GENERATION_ATTEMPTS = 5


def _generate_unique_public_key(db: Session) -> str:
    for _ in range(MAX_KEY_GENERATION_ATTEMPTS):
        public_key = generate_public_key()
        existing = db.query(APIKey).filter(APIKey.public_key == public_key).first()
        if not existing:
            return public_key
    raise RuntimeError("Unable to generate a unique public key.")


def _create_api_key_record(
    db: Session,
    *,
    tenant_id: int,
    website_id: int,
    environment_id: int,
    name: str | None,
    created_by_user_id: int | None,
) -> tuple[APIKey, str]:
    public_key = _generate_unique_public_key(db)
    raw_secret = generate_secret()
    api_key = APIKey(
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=environment_id,
        public_key=public_key,
        secret_hash=hash_secret(raw_secret),
        name=name,
        status="active",
        created_by_user_id=created_by_user_id,
    )
    db.add(api_key)
    return api_key, raw_secret


def create_api_key(
    db: Session,
    tenant_id: int,
    website_id: int,
    environment_id: int,
    name: str | None = None,
    created_by_user_id: int | None = None,
) -> tuple[APIKey, str]:
    api_key, raw_secret = _create_api_key_record(
        db,
        tenant_id=tenant_id,
        website_id=website_id,
        environment_id=environment_id,
        name=name,
        created_by_user_id=created_by_user_id,
    )
    db.commit()
    db.refresh(api_key)
    return api_key, raw_secret


def list_api_keys(
    db: Session,
    tenant_id: int,
    website_id: int | None = None,
    environment_id: int | None = None,
) -> list[APIKey]:
    query = scoped_query(db, APIKey, tenant_id)
    if website_id is not None:
        query = query.filter(APIKey.website_id == website_id)
    if environment_id is not None:
        query = query.filter(APIKey.environment_id == environment_id)
    return query.order_by(APIKey.created_at.desc()).all()


def get_api_key_by_public_key(db: Session, public_key: str) -> APIKey | None:
    return db.query(APIKey).filter(APIKey.public_key == public_key).first()


def revoke_api_key(
    db: Session,
    tenant_id: int,
    api_key_id: int,
    revoked_by_user_id: int | None = None,
) -> APIKey:
    api_key = get_tenant_owned_or_404(db, APIKey, tenant_id, api_key_id)
    api_key.revoked_at = datetime.now(timezone.utc)
    api_key.revoked_by_user_id = revoked_by_user_id
    api_key.status = "revoked"
    db.commit()
    db.refresh(api_key)
    return api_key


def rotate_api_key(
    db: Session,
    tenant_id: int,
    api_key_id: int,
    created_by_user_id: int | None = None,
) -> tuple[APIKey, str]:
    api_key = get_tenant_owned_or_404(db, APIKey, tenant_id, api_key_id)
    api_key.revoked_at = datetime.now(timezone.utc)
    api_key.revoked_by_user_id = created_by_user_id
    api_key.status = "revoked"
    new_key, raw_secret = _create_api_key_record(
        db,
        tenant_id=tenant_id,
        website_id=api_key.website_id,
        environment_id=api_key.environment_id,
        name=api_key.name,
        created_by_user_id=created_by_user_id,
    )
    db.commit()
    db.refresh(new_key)
    return new_key, raw_secret


def mark_api_key_used(db: Session, public_key: str) -> APIKey | None:
    api_key = db.query(APIKey).filter(APIKey.public_key == public_key).first()
    if not api_key:
        return None
    api_key.last_used_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(api_key)
    return api_key
