"""
Trusted client IP extraction helpers.
"""

from __future__ import annotations

from ipaddress import ip_address, ip_network
from typing import Iterable

from fastapi import Request

from app.core.config import settings


def _parse_ip(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(ip_address(value.strip()))
    except ValueError:
        return None


def _is_public(ip_value: str) -> bool:
    return ip_address(ip_value).is_global


def _first_ip_from_xff(value: str) -> str | None:
    if not value:
        return None
    candidates = [part.strip() for part in value.split(",") if part.strip()]
    first_valid = None
    for candidate in candidates:
        parsed = _parse_ip(candidate)
        if not parsed:
            continue
        if first_valid is None:
            first_valid = parsed
        if _is_public(parsed):
            return parsed
    return first_valid


def _peer_is_trusted(peer: str | None, trusted: Iterable[str]) -> bool:
    parsed_peer = _parse_ip(peer)
    if not parsed_peer:
        return False
    peer_ip = ip_address(parsed_peer)
    for entry in trusted:
        try:
            network = ip_network(entry, strict=False)
        except ValueError:
            continue
        if peer_ip in network:
            return True
    return False


def extract_client_ip(request: Request) -> str | None:
    """
    Resolve the real client IP based on proxy trust settings.
    """
    peer = request.client.host if request.client else None
    if not settings.TRUST_PROXY_HEADERS:
        return _parse_ip(peer)

    if not _peer_is_trusted(peer, settings.TRUSTED_PROXY_IPS):
        return _parse_ip(peer)

    for header in settings.TRUSTED_IP_HEADERS:
        raw = request.headers.get(header)
        if not raw:
            continue
        if header.lower() == "x-forwarded-for":
            parsed = _first_ip_from_xff(raw)
        else:
            parsed = _parse_ip(raw.split(",")[0])
        if parsed:
            return parsed

    return _parse_ip(peer)
