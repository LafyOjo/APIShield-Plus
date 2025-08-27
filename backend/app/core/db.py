# This file sets up the SQLAlchemy database connection and
# session handling. It knows how to connect depending on the
# DB type (SQLite vs Postgres/MySQL). Every request handler
# can use `get_db()` to grab a safe session.

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool
from app.core.config import Settings

# Pull settings once so we can read DATABASE_URL and other flags.
settings = Settings()

# Control whether SQLAlchemy prints out raw SQL (useful for debugging).
# We let users toggle via DB_ECHO env var, default is "false".
_echo_env = os.getenv("DB_ECHO", "false").lower()
ECHO = _echo_env in {"1", "true", "yes"}

# The DB connection string, e.g. "sqlite:///./app.db" or Postgres URL.
DATABASE_URL = settings.DATABASE_URL

# Build an engine depending on whether it's SQLite or something else.
# SQLite needs special thread handling and works better without pooling.
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},  # SQLite doesn’t like threads by default
        poolclass=NullPool,  # Disable pooling so dev environments don’t hit weird errors
        echo=ECHO,
        future=True,
    )
else:
    # For real DBs (Postgres/MySQL), use a connection pool with pre-ping
    # and configurable pool sizes. This makes the app scale safely.
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,  # Helps recycle dead connections
        pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
        pool_recycle=1800,   # Recycle every 30 minutes
        echo=ECHO,
        future=True,
    )

# SessionLocal gives us a factory for DB sessions. Each request gets one,
# and `autoflush`/`autocommit` are kept off for safer transaction control.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Base is where all our ORM models will inherit from. Think of it as
# the foundation for every table mapping.
Base = declarative_base()

def get_db():
    # Dependency injection helper for FastAPI.
    # Yields a session and ensures it’s closed after the request.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
