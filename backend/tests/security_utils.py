from __future__ import annotations


def assert_endpoint_requires_role(
    client,
    method: str,
    url: str,
    *,
    allowed_token: str,
    denied_token: str,
    tenant_header: str,
    json_body: dict | None = None,
    expected_allowed: set[int] | None = None,
    expected_denied: set[int] | None = None,
) -> None:
    expected_allowed = expected_allowed or {200, 201, 202, 204}
    expected_denied = expected_denied or {403, 404}

    denied_resp = client.request(
        method,
        url,
        headers={"Authorization": f"Bearer {denied_token}", "X-Tenant-ID": tenant_header},
        json=json_body,
    )
    assert denied_resp.status_code in expected_denied

    allowed_resp = client.request(
        method,
        url,
        headers={"Authorization": f"Bearer {allowed_token}", "X-Tenant-ID": tenant_header},
        json=json_body,
    )
    assert allowed_resp.status_code in expected_allowed
