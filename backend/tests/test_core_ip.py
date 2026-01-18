import os
from starlette.requests import Request

os.environ.setdefault("SKIP_MIGRATIONS", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.config import settings
from app.core.ip import extract_client_ip


def _make_request(headers=None, client_host="203.0.113.10"):
    raw_headers = []
    if headers:
        raw_headers = [
            (k.lower().encode("ascii"), v.encode("ascii")) for k, v in headers.items()
        ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": raw_headers,
        "client": (client_host, 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
        "root_path": "",
    }
    return Request(scope)


def test_extract_client_ip_direct_connection(monkeypatch):
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", False)
    req = _make_request(client_host="203.0.113.10")
    assert extract_client_ip(req) == "203.0.113.10"


def test_extract_client_ip_trusted_proxy_uses_forwarded_headers(monkeypatch):
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", ["10.0.0.0/8"])
    monkeypatch.setattr(settings, "TRUSTED_IP_HEADERS", ["X-Forwarded-For"])
    req = _make_request(
        headers={"X-Forwarded-For": "1.1.1.1, 10.0.0.5"},
        client_host="10.0.0.5",
    )
    assert extract_client_ip(req) == "1.1.1.1"


def test_extract_client_ip_untrusted_proxy_ignores_forwarded_headers(monkeypatch):
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", ["10.0.0.0/8"])
    monkeypatch.setattr(settings, "TRUSTED_IP_HEADERS", ["X-Forwarded-For"])
    req = _make_request(
        headers={"X-Forwarded-For": "1.1.1.1, 10.0.0.5"},
        client_host="203.0.113.10",
    )
    assert extract_client_ip(req) == "203.0.113.10"


def test_extract_client_ip_parses_x_forwarded_for_chain_safely(monkeypatch):
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(settings, "TRUSTED_PROXY_IPS", ["10.0.0.0/8"])
    monkeypatch.setattr(settings, "TRUSTED_IP_HEADERS", ["X-Forwarded-For"])
    req = _make_request(
        headers={"X-Forwarded-For": "10.0.0.2, unknown, 8.8.8.8, 192.168.0.1"},
        client_host="10.0.0.5",
    )
    assert extract_client_ip(req) == "8.8.8.8"
