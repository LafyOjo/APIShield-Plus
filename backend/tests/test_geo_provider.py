import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.core.config import settings
from app.geo.provider import ApiGeoProvider, GeoResult, LocalGeoProvider, get_geo_provider


def test_geo_provider_interface_returns_georesult_shape():
    provider = LocalGeoProvider("/tmp/geo-city.mmdb", "/tmp/geo-asn.mmdb")
    result = provider.lookup("8.8.8.8")
    assert isinstance(result, GeoResult)
    assert result.country_code is None
    assert result.asn_org is None


def test_geo_config_selects_provider(monkeypatch):
    monkeypatch.setattr(settings, "GEO_PROVIDER", "local")
    monkeypatch.setattr(settings, "GEO_DB_PATH", "/tmp/city.mmdb")
    monkeypatch.setattr(settings, "GEO_ASN_DB_PATH", "/tmp/asn.mmdb")
    provider = get_geo_provider()
    assert isinstance(provider, LocalGeoProvider)
    assert provider.city_db_path == "/tmp/city.mmdb"

    monkeypatch.setattr(settings, "GEO_PROVIDER", "api")
    monkeypatch.setattr(settings, "GEO_API_KEY", "demo-key")
    monkeypatch.setattr(settings, "GEO_API_BASE_URL", "https://geo.example.com")
    provider = get_geo_provider()
    assert isinstance(provider, ApiGeoProvider)
    assert provider.api_base_url == "https://geo.example.com"
