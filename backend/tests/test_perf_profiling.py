import logging
import os

from fastapi.testclient import TestClient
from sqlalchemy import text

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "secret")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from app.main import app
from app.core.db import engine
import app.core.access_log as access_log_module
import app.core.logging as logging_module
import app.core.perf as perf_module


class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def test_perf_profile_fields_present_when_enabled():
    handler = ListHandler()
    logger = logging_module.logger
    original_handlers = list(logger.handlers)
    original_level = logger.level
    original_propagate = logger.propagate
    original_perf_flag = logging_module.settings.PERF_PROFILING
    original_perf_flag_perf = perf_module.settings.PERF_PROFILING
    original_create_access_log = access_log_module.create_access_log

    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logging_module.settings.PERF_PROFILING = True
    perf_module.settings.PERF_PROFILING = True
    access_log_module.create_access_log = lambda db, username, path: None

    try:
        client = TestClient(app)
        resp = client.get("/ping")
        assert resp.status_code == 200
        record = next(
            (rec for rec in handler.records if rec.getMessage() == "request.completed"),
            None,
        )
        assert record is not None
        assert hasattr(record, "db_time_ms")
        assert hasattr(record, "db_queries_count")
        assert hasattr(record, "handler_time_ms")
        assert hasattr(record, "serialize_time_ms")
    finally:
        logger.handlers = original_handlers
        logger.setLevel(original_level)
        logger.propagate = original_propagate
        logging_module.settings.PERF_PROFILING = original_perf_flag
        perf_module.settings.PERF_PROFILING = original_perf_flag_perf
        access_log_module.create_access_log = original_create_access_log


def test_db_query_count_increments_with_profiling_enabled():
    original_perf_flag = perf_module.settings.PERF_PROFILING
    try:
        perf_module.settings.PERF_PROFILING = True
        perf_module.start_request(
            route="/test",
            method="GET",
            request_id="req-1",
            tenant_id="tenant-1",
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        stats = perf_module.finish_request()
        assert stats is not None
        assert stats.db_queries_count >= 1
        assert isinstance(stats.db_time_ms, float)
        assert stats.db_time_ms >= 0.0
    finally:
        perf_module.settings.PERF_PROFILING = original_perf_flag


def test_slow_query_fingerprint_logged_when_threshold_hit():
    handler = ListHandler()
    perf_logger = perf_module._get_perf_logger()
    original_handlers = list(perf_logger.handlers)
    original_level = perf_logger.level
    original_propagate = perf_logger.propagate
    original_perf_flag = perf_module.settings.PERF_PROFILING
    original_threshold = perf_module.settings.PERF_SLOW_QUERY_MS
    original_limit = perf_module.settings.PERF_SLOW_QUERY_MAX_PER_REQUEST

    perf_logger.handlers = [handler]
    perf_logger.setLevel(logging.WARNING)
    perf_logger.propagate = False
    perf_module.settings.PERF_PROFILING = True
    perf_module.settings.PERF_SLOW_QUERY_MS = 0
    perf_module.settings.PERF_SLOW_QUERY_MAX_PER_REQUEST = 1

    try:
        perf_module.start_request(
            route="/slow",
            method="GET",
            request_id="req-slow",
            tenant_id="tenant-2",
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        perf_module.finish_request()
        record = next(
            (rec for rec in handler.records if rec.getMessage() == "db.slow_query"),
            None,
        )
        assert record is not None
        assert hasattr(record, "query_fingerprint")
        assert getattr(record, "path", None) == "/slow"
    finally:
        perf_logger.handlers = original_handlers
        perf_logger.setLevel(original_level)
        perf_logger.propagate = original_propagate
        perf_module.settings.PERF_PROFILING = original_perf_flag
        perf_module.settings.PERF_SLOW_QUERY_MS = original_threshold
        perf_module.settings.PERF_SLOW_QUERY_MAX_PER_REQUEST = original_limit


def test_slow_query_fingerprint_strips_literals():
    handler = ListHandler()
    perf_logger = perf_module._get_perf_logger()
    original_handlers = list(perf_logger.handlers)
    original_level = perf_logger.level
    original_propagate = perf_logger.propagate
    original_perf_flag = perf_module.settings.PERF_PROFILING
    original_threshold = perf_module.settings.PERF_SLOW_QUERY_MS
    original_limit = perf_module.settings.PERF_SLOW_QUERY_MAX_PER_REQUEST

    perf_logger.handlers = [handler]
    perf_logger.setLevel(logging.WARNING)
    perf_logger.propagate = False
    perf_module.settings.PERF_PROFILING = True
    perf_module.settings.PERF_SLOW_QUERY_MS = 0
    perf_module.settings.PERF_SLOW_QUERY_MAX_PER_REQUEST = 1

    try:
        perf_module.start_request(
            route="/slow",
            method="GET",
            request_id="req-slow-2",
            tenant_id="tenant-3",
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 'supersecret' AS s, 123 AS n"))
        perf_module.finish_request()
        record = next(
            (rec for rec in handler.records if rec.getMessage() == "db.slow_query"),
            None,
        )
        assert record is not None
        fingerprint = getattr(record, "query_fingerprint", "")
        assert "supersecret" not in fingerprint
        assert "123" not in fingerprint
    finally:
        perf_logger.handlers = original_handlers
        perf_logger.setLevel(original_level)
        perf_logger.propagate = original_propagate
        perf_module.settings.PERF_PROFILING = original_perf_flag
        perf_module.settings.PERF_SLOW_QUERY_MS = original_threshold
        perf_module.settings.PERF_SLOW_QUERY_MAX_PER_REQUEST = original_limit
