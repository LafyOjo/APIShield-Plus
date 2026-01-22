import os
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config


def _make_alembic_config(db_url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[1]
    backend_dir = repo_root / "backend"
    alembic_ini = backend_dir / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", db_url)
    config.set_main_option("prepend_sys_path", str(backend_dir))
    return config


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "migration_smoke.db"
        db_url = f"sqlite:///{db_path}"
        os.environ["DATABASE_URL"] = db_url
        os.environ["SECRET_KEY"] = os.getenv("SECRET_KEY", "smoke-test-secret")

        config = _make_alembic_config(db_url)
        command.upgrade(config, "head")
        command.downgrade(config, "-1")
        command.upgrade(config, "head")
        print("Migration smoke test passed.")


if __name__ == "__main__":
    main()
