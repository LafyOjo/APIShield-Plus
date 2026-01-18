import secrets
import hashlib
import hmac

from app.core.config import settings
from app.core.security import get_password_hash, verify_password


def generate_public_key() -> str:
    return f"pk_{secrets.token_urlsafe(24)}"


def generate_secret() -> str:
    return f"sk_{secrets.token_urlsafe(32)}"


def hash_secret(secret: str) -> str:
    return get_password_hash(secret)


def verify_secret(secret: str, secret_hash: str) -> bool:
    return verify_password(secret, secret_hash)


def generate_invite_token() -> str:
    return f"inv_{secrets.token_urlsafe(32)}"


def hash_token(token: str) -> str:
    digest = hmac.new(settings.SECRET_KEY.encode(), token.encode(), hashlib.sha256)
    return digest.hexdigest()


def verify_token(token: str, token_hash: str) -> bool:
    expected = hash_token(token)
    return hmac.compare_digest(expected, token_hash)
