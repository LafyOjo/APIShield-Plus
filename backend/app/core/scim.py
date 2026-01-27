import secrets

from app.core.security import get_password_hash, verify_password


def generate_scim_token() -> str:
    return f"scim_{secrets.token_urlsafe(32)}"


def hash_scim_token(token: str) -> str:
    return get_password_hash(token)


def verify_scim_token(token: str, token_hash: str) -> bool:
    if not token_hash:
        return False
    return verify_password(token, token_hash)
