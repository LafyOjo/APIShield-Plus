from sqlalchemy.orm import Session

from app.models.website_environments import WebsiteEnvironment


def _normalize_env_name(name: str) -> str:
    return name.strip().lower()


def create_environment(
    db: Session,
    website_id: int,
    name: str,
    base_url: str | None = None,
) -> WebsiteEnvironment:
    normalized = _normalize_env_name(name)
    existing = (
        db.query(WebsiteEnvironment)
        .filter(WebsiteEnvironment.website_id == website_id, WebsiteEnvironment.name == normalized)
        .first()
    )
    if existing:
        raise ValueError("Environment already exists for website.")
    env = WebsiteEnvironment(website_id=website_id, name=normalized, base_url=base_url)
    db.add(env)
    db.commit()
    db.refresh(env)
    return env


def list_environments(db: Session, website_id: int) -> list[WebsiteEnvironment]:
    return (
        db.query(WebsiteEnvironment)
        .filter(WebsiteEnvironment.website_id == website_id)
        .order_by(WebsiteEnvironment.id)
        .all()
    )


def get_environment(db: Session, website_id: int, env_id: int) -> WebsiteEnvironment | None:
    return (
        db.query(WebsiteEnvironment)
        .filter(
            WebsiteEnvironment.website_id == website_id,
            WebsiteEnvironment.id == env_id,
        )
        .first()
    )


def update_environment(
    db: Session,
    website_id: int,
    env_id: int,
    *,
    name: str | None = None,
    base_url: str | None = None,
    status: str | None = None,
) -> WebsiteEnvironment | None:
    env = get_environment(db, website_id, env_id)
    if not env:
        return None
    if name is not None:
        env.name = _normalize_env_name(name)
    if base_url is not None:
        env.base_url = base_url
    if status is not None:
        env.status = status
    db.commit()
    db.refresh(env)
    return env
