from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.is_sqlite else {}
if settings.is_sqlite:
    # A missing directory is a confusing startup failure; create it for local dev.
    database_path = make_url(settings.database_url).database
    if database_path and database_path != ":memory:":
        Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
)

if settings.is_sqlite:

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    # Importing registers all mappers. create_all is fine for this starter;
    # run Alembic (or another migration tool) before evolving a live schema.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_tenant_columns()


def _ensure_tenant_columns() -> None:
    """Additive migration for databases created before the portal existed.

    ``create_all`` never alters an existing table. These two nullable columns
    are safe to add in place on both SQLite and PostgreSQL; a full Alembic
    migration is still the right move before a production schema change.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table in ("customers", "conversations"):
        if table not in existing_tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "tenant_id" in columns:
            continue
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN tenant_id VARCHAR(64)"))
            connection.execute(
                text(f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id ON {table} (tenant_id)")
            )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
