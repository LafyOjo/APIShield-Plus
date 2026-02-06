from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def _b64decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def load_private_key(encoded: str) -> Ed25519PrivateKey:
    raw = _b64decode(encoded.strip())
    if len(raw) != 32:
        raise ValueError("Invalid private key length")
    return Ed25519PrivateKey.from_private_bytes(raw)


def load_public_key(encoded: str) -> Ed25519PublicKey:
    raw = _b64decode(encoded.strip())
    if len(raw) != 32:
        raise ValueError("Invalid public key length")
    return Ed25519PublicKey.from_public_bytes(raw)


def sign_payload(payload: dict[str, Any], private_key: Ed25519PrivateKey) -> str:
    signature = private_key.sign(canonical_json(payload))
    return _b64encode(signature)


def verify_signature(payload: dict[str, Any], signature: str, public_key: Ed25519PublicKey) -> bool:
    try:
        public_key.verify(_b64decode(signature), canonical_json(payload))
        return True
    except Exception:
        return False
