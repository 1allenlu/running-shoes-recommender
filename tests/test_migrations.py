import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.db.models import Base


def alembic_config() -> Config:
    return Config("alembic.ini")


def test_offline_sql_creates_all_tables(capsys):
    command.upgrade(alembic_config(), "head", sql=True)
    sql = capsys.readouterr().out
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    for table in Base.metadata.tables:
        assert f"CREATE TABLE {table} (" in sql
    assert "USING hnsw (embedding vector_cosine_ops)" in sql


@pytest.mark.db
def test_upgrade_matches_models_and_downgrades(db_url):
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == [], f"migration and models disagree: {diff}"

        command.downgrade(cfg, "base")
        assert set(inspect(engine).get_table_names()) <= {"alembic_version"}
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()
