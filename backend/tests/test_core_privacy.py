import os

os.environ.setdefault("SKIP_MIGRATIONS", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "secret")

from app.core.privacy import hash_ip


def test_hash_ip_deterministic_for_same_tenant():
    first = hash_ip(1, "203.0.113.10")
    second = hash_ip(1, "203.0.113.10")
    assert first == second


def test_hash_ip_differs_across_tenants():
    tenant_a = hash_ip(1, "203.0.113.10")
    tenant_b = hash_ip(2, "203.0.113.10")
    assert tenant_a != tenant_b


def test_hash_ip_handles_ipv4_ipv6():
    ipv4_hash = hash_ip(1, "198.51.100.1")
    ipv6_hash = hash_ip(1, "2001:db8::1")
    assert ipv4_hash != ipv6_hash
