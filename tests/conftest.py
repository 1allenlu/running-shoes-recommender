import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.config import get_settings


@pytest.fixture(scope="session")
def db_url() -> str:
    """DATABASE_URL, or skip when no Postgres is reachable (e.g. without `docker compose up`)."""
    url = get_settings().database_url
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip(f"Postgres not reachable at {url}")
    finally:
        engine.dispose()
    return url
