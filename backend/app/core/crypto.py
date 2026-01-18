import base64
import json
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


_fernet: Fernet | None = None


def _load_key() -> bytes:
    key_value = settings.INTEGRATION_ENCRYPTION_KEY or os.getenv("INTEGRATION_ENCRYPTION_KEY")
    if not key_value:
        raise ValueError("INTEGRATION_ENCRYPTION_KEY is not set")
    if isinstance(key_value, str):
        key_bytes = key_value.encode("utf-8")
    else:
        key_bytes = key_value
    if len(key_bytes) == 32:
        key_bytes = base64.urlsafe_b64encode(key_bytes)
    return key_bytes


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        try:
            _fernet = Fernet(_load_key())
        except Exception as exc:
            raise ValueError("Invalid INTEGRATION_ENCRYPTION_KEY") from exc
    return _fernet


def encrypt_json(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    token = _get_fernet().encrypt(serialized.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_json(token: str) -> dict[str, Any]:
    try:
        raw = _get_fernet().decrypt(token.encode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("Invalid encrypted payload") from exc
    return json.loads(raw.decode("utf-8"))
