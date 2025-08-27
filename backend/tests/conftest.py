import os
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

# Ensure the backend package is on the Python path so tests can import app.*
backend_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_root))


@pytest.fixture(autouse=True)
def apply_migrations():
    """Apply Alembic migrations for a clean database before each test."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        # Tests that don't touch the DB can skip migrations.
        yield
        return

    from app.core.db import SessionLocal

    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")
    try:
        yield
    finally:
        SessionLocal().close()
        command.downgrade(cfg, "base")
