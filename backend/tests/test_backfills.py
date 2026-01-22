import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _make_alembic_config(db_url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    alembic_ini = backend_dir / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", db_url)
    config.set_main_option("prepend_sys_path", str(backend_dir))
    return config


def test_backfill_run_records_progress_and_resumes(tmp_path):
    db_path = tmp_path / "backfill_runs.db"
    db_url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = db_url
    os.environ["SECRET_KEY"] = "secret"

    config = _make_alembic_config(db_url)
    command.upgrade(config, "head")

    from app.jobs.backfills.base import (
        finish_backfill,
        record_backfill_progress,
        resume_or_start_backfill,
    )

    engine = create_engine(db_url, future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)
    db = SessionLocal()
    try:
        run = resume_or_start_backfill(db, "demo_job")
        assert run.last_id_processed is None

        record_backfill_progress(db, run, 120)
        run_again = resume_or_start_backfill(db, "demo_job")
        assert run_again.id == run.id
        assert run_again.last_id_processed == 120

        finish_backfill(db, run_again)
        resumed = resume_or_start_backfill(db, "demo_job")
        assert resumed.id != run_again.id
        assert resumed.last_id_processed is None
    finally:
        db.close()
        engine.dispose()
