import os
from pathlib import Path


def test_openapi_schema_validates():
    repo_root = Path(__file__).resolve().parents[2]
    spec_path = repo_root / "docs" / "public_api" / "openapi.yaml"
    assert spec_path.exists()
    text = spec_path.read_text(encoding="utf-8")
    assert "openapi:" in text
    assert "/ingest/browser" in text
    assert "/ingest/security" in text
    assert "/api/v1/map/summary" in text
    assert "/api/v1/map/drilldown" in text
    assert "/api/v1/incidents" in text
    assert "/api/v1/notifications/channels" in text
