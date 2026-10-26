"""Alembic migration reproducibility: upgrade head + downgrade base against a
throwaway database."""

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic import command
from alembic.config import Config

from app.core.config import BASE_DIR, settings

EXPECTED_TABLES = {
    "users",
    "workers",
    "complaints",
    "ai_recommendations",
    "tasks",
    "status_history",
    "alerts",
}


@pytest.fixture()
def migration_db(tmp_path, monkeypatch):
    db_file = tmp_path / "migration-check.db"
    url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setattr(settings, "database_url", url)

    config = Config(str(BASE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BASE_DIR / "alembic"))
    return url, config


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_head_creates_all_tables(migration_db):
    url, config = migration_db
    command.upgrade(config, "head")

    tables = _tables(url)
    assert EXPECTED_TABLES <= tables
    assert "alembic_version" in tables

    # A second upgrade run must be a no-op (reproducible).
    command.upgrade(config, "head")
    assert EXPECTED_TABLES <= _tables(url)


def test_downgrade_base_removes_tables(migration_db):
    url, config = migration_db
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            remaining = set(
                connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type = 'table'")
                ).scalars()
            )
    finally:
        engine.dispose()
    assert not EXPECTED_TABLES & remaining
