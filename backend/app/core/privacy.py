"""
IP hashing and masking helpers for privacy-safe correlation.
"""

from __future__ import annotations

import hashlib
import hmac
from ipaddress import ip_address, ip_network

from app.core.config import settings


def _normalize_ip(value: str) -> str:
    if not value or not value.strip():
        raise ValueError("ip value is required")
    return str(ip_address(value.strip()))


def tenant_ip_salt(tenant_id: int) -> bytes:
    if tenant_id is None:
        raise ValueError("tenant_id is required for ip hashing")
    secret = settings.SECRET_KEY.encode("utf-8")
    message = f"tenant:{tenant_id}".encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).digest()


def hash_ip(tenant_id: int, ip_str: str) -> str:
    normalized = _normalize_ip(ip_str)
    salt = tenant_ip_salt(tenant_id)
    return hmac.new(salt, normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def mask_ip(ip_str: str) -> str:
    normalized = _normalize_ip(ip_str)
    parsed = ip_address(normalized)
    if parsed.version == 4:
        network = ip_network(f"{parsed}/24", strict=False)
        return f"{network.network_address}/24"
    network = ip_network(f"{parsed}/64", strict=False)
    return f"{network.network_address}/64"
