import logging
import os

from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.main import app  # noqa: E402


def test_logging_includes_request_id_and_tenant_id(caplog):
    logger = logging.getLogger("api_logger")
    logger.addHandler(caplog.handler)
    logger.setLevel(logging.INFO)
    try:
        client = TestClient(app)
        response = client.get(
            "/ping",
            headers={
                "X-Request-ID": "req-123",
                "X-Tenant-ID": "tenant-42",
            },
        )
        assert response.status_code == 200

        records = []
        for record in caplog.records:
            if record.getMessage() == "request.completed":
                records.append(record)

        assert records, "Expected a structured request log entry"
        entry = records[-1]
        assert getattr(entry, "request_id", None) == "req-123"
        assert getattr(entry, "tenant_id", None) == "tenant-42"
        assert getattr(entry, "status_code", None) == 200
    finally:
        logger.removeHandler(caplog.handler)
