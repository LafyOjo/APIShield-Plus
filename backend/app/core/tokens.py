import secrets

from app.core.security import get_password_hash, verify_password


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return get_password_hash(token)


def verify_token(token: str, token_hash: str) -> bool:
    return verify_password(token, token_hash)
