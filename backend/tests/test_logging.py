import logging
import os

from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret")

from app.main import app  # noqa: E402
import app.core.access_log as access_log_module  # noqa: E402
import app.core.logging as logging_module  # noqa: E402


def test_logging_includes_request_id_and_tenant_id(caplog):
    logger = logging.getLogger("api_logger")
    logger.addHandler(caplog.handler)
    logger.setLevel(logging.INFO)
    original_create_access_log = access_log_module.create_access_log
    access_log_module.create_access_log = lambda db, username, path: None
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
        assert response.headers.get("X-Request-ID") == "req-123"

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
        access_log_module.create_access_log = original_create_access_log
        logger.removeHandler(caplog.handler)


def test_logging_hides_perf_fields_when_disabled(caplog):
    logger = logging.getLogger("api_logger")
    logger.addHandler(caplog.handler)
    logger.setLevel(logging.INFO)
    original_create_access_log = access_log_module.create_access_log
    access_log_module.create_access_log = lambda db, username, path: None
    original_perf_flag = logging_module.settings.PERF_PROFILING
    logging_module.settings.PERF_PROFILING = False
    try:
        client = TestClient(app)
        response = client.get("/ping")
        assert response.status_code == 200
        record = next(
            (rec for rec in caplog.records if rec.getMessage() == "request.completed"),
            None,
        )
        assert record is not None
        assert not hasattr(record, "db_time_ms")
        assert not hasattr(record, "db_queries_count")
        assert not hasattr(record, "handler_time_ms")
        assert not hasattr(record, "serialize_time_ms")
    finally:
        logging_module.settings.PERF_PROFILING = original_perf_flag
        access_log_module.create_access_log = original_create_access_log
        logger.removeHandler(caplog.handler)
