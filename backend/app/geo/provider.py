from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.config import settings


@dataclass(frozen=True)
class GeoResult:
    country_code: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    asn_number: Optional[int] = None
    asn_org: Optional[str] = None
    is_datacenter: Optional[bool] = None
    accuracy_note: Optional[str] = None


class GeoProvider:
    def lookup(self, ip_str: str) -> GeoResult:
        raise NotImplementedError


class LocalGeoProvider(GeoProvider):
    def __init__(self, city_db_path: str, asn_db_path: Optional[str]) -> None:
        self.city_db_path = city_db_path
        self.asn_db_path = asn_db_path

    def lookup(self, ip_str: str) -> GeoResult:
        # TODO: Implement local MMDB lookup using the configured DB paths.
        return GeoResult()


class ApiGeoProvider(GeoProvider):
    def __init__(self, api_key: Optional[str], api_base_url: Optional[str]) -> None:
        self.api_key = api_key
        self.api_base_url = api_base_url

    def lookup(self, ip_str: str) -> GeoResult:
        # TODO: Implement API lookup using the configured provider.
        return GeoResult()


_provider: GeoProvider | None = None
_provider_signature: tuple | None = None


def _get_signature() -> tuple:
    return (
        (settings.GEO_PROVIDER or "local").lower(),
        settings.GEO_DB_PATH,
        settings.GEO_ASN_DB_PATH,
        settings.GEO_API_BASE_URL,
        settings.GEO_API_KEY,
    )


def get_geo_provider() -> GeoProvider:
    global _provider, _provider_signature
    signature = _get_signature()
    if _provider is None or signature != _provider_signature:
        _provider = _build_geo_provider(signature[0])
        _provider_signature = signature
    return _provider


def _build_geo_provider(provider_name: str) -> GeoProvider:
    if provider_name == "local":
        return LocalGeoProvider(settings.GEO_DB_PATH, settings.GEO_ASN_DB_PATH)
    if provider_name == "api":
        return ApiGeoProvider(settings.GEO_API_KEY, settings.GEO_API_BASE_URL)
    raise ValueError(f"Unsupported GEO_PROVIDER: {provider_name}")
