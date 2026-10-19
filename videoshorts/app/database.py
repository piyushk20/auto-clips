"""
database.py — SQLAlchemy engine and session for VideoShorts.
Uses SQLite with WAL mode for concurrent reads.
"""
from __future__ import annotations

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 30.0},
)


# Enable WAL mode and busy timeout for concurrent read/write stability
@event.listens_for(engine, "connect")
def _set_wal_mode(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """Create all tables on startup (idempotent) and auto-migrate missing columns."""
    from app.models import job  # noqa: F401 — imports ORM models to register them
    Base.metadata.create_all(bind=engine)

    # Lightweight auto-migration for SQLite columns
    with engine.connect() as conn:
        try:
            res = conn.execute(text("PRAGMA table_info(jobs)"))
            cols = {row[1] for row in res.fetchall()}
            if cols and "min_score" not in cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN min_score REAL NOT NULL DEFAULT 0.72"))
            if cols and "pacing" not in cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN pacing TEXT NOT NULL DEFAULT 'punchy'"))
            conn.commit()
        except Exception:
            pass

