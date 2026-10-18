import os

# Tests drop and recreate tables, so never point them at the dev database.
# Set before any `app` import: env vars take priority over `.env`.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://shoe:shoe@localhost:5432/shoe_test"
)

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import get_settings  # noqa: E402


@pytest.fixture(scope="session")
def db_url() -> str:
    """Migrated test database URL, or skip when no Postgres is reachable."""
    url = get_settings().database_url
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip(f"Postgres not reachable at {url}")
    finally:
        engine.dispose()
    command.upgrade(Config("alembic.ini"), "head")
    return url


@pytest.fixture
def db_session(db_url):
    """Session on an empty schema; tables are truncated after each test."""
    engine = create_engine(db_url)
    with Session(engine) as session:
        yield session
        session.rollback()
        session.execute(
            text(
                "TRUNCATE shoes, fit_notes, size_charts, offers, users, scans, tasks, feedback "
                "RESTART IDENTITY CASCADE"
            )
        )
        session.commit()
    engine.dispose()


SHOES_HEADER = (
    "brand,model,version,category,drop_mm,stack_heel_mm,stack_forefoot_mm,weight_g,"
    "widths_available,toe_box,upper_volume,heel_lock,price_usd\n"
)


@pytest.fixture
def seed_dir(tmp_path: Path) -> Path:
    (tmp_path / "shoes.csv").write_text(
        SHOES_HEADER
        + "Acme,Glide,2,daily,8,38,30,250,standard|wide,roomy,low,true,140\n"
        + "Acme,Zoom,1,race,TODO,TODO,TODO,TODO,TODO,TODO,TODO,TODO,TODO\n"
    )
    (tmp_path / "fit_notes.jsonl").write_text(
        '{"brand": "Acme", "model": "Glide", "version": "2", "source": "s", "text": "roomy"}\n'
        '{"brand": "Acme", "model": "Glide", "version": "2", "source": "s", "text": "soft"}\n'
        '{"brand": "Acme", "model": "Glide", "version": "2", "source": "s", "text": "secure"}\n'
    )
    (tmp_path / "size_charts.csv").write_text(
        "brand,us_size,length_mm_min,length_mm_max,sizing_note\n"
        "Acme,9.0,268,272,true to size\n"
        "Acme,9.5,TODO,TODO,TODO\n"
    )
    return tmp_path


# --- A small catalog with known specs, size charts and offers, for agent/API/search tests ---

FAKE_SHOES = [
    # brand, model, version, category, drop, widths, toe_box, upper_volume, heel_lock, price
    ("Acme", "Roomy", "1", "daily", "6", "standard|wide", "roomy", "low", "true", "140"),
    ("Acme", "Narrow", "2", "daily", "8", "standard", "narrow", "medium", "true", "130"),
    ("Acme", "Plush", "3", "max-cushion", "8", "standard|wide|extra-wide", "medium", "high",
     "true", "170"),
    ("Bolt", "Tempo", "4", "tempo", "TODO", "TODO", "TODO", "TODO", "TODO", "150"),
    ("Bolt", "Daily", "5", "daily", "10", "standard|wide", "roomy", "medium", "true", "120"),
]  # fmt: skip
FAKE_NOTES = {
    ("Acme", "Roomy", "1"): ["roomy toe box lets toes splay", "snug low volume upper",
                             "secure heel lock"],
    ("Acme", "Narrow", "2"): ["narrow tight forefoot", "medium volume upper", "soft cushioning"],
    ("Acme", "Plush", "3"): ["plush high volume upper", "soft max cushion for long runs",
                             "roomy forefoot"],
    ("Bolt", "Tempo", "4"): ["light fast tempo shoe", "firm snappy ride", "low volume race fit"],
    ("Bolt", "Daily", "5"): ["roomy toe box", "balanced cushioning", "secure heel"],
}  # fmt: skip


def reference_mid_mm(size: float) -> float:
    return 250 + (size - 7) * 8.4


def write_fake_seed(seed: Path) -> None:
    import json

    seed.mkdir(parents=True, exist_ok=True)
    (seed / "shoes.csv").write_text(
        SHOES_HEADER
        + "".join(
            f"{b},{m},{v},{c},{d},30,22,250,{w},{t},{u},{h},{p}\n"
            for b, m, v, c, d, w, t, u, h, p in FAKE_SHOES
        )
    )
    (seed / "fit_notes.jsonl").write_text(
        "".join(
            json.dumps({"brand": b, "model": m, "version": v, "source": "test", "text": text})
            + "\n"
            for (b, m, v), texts in FAKE_NOTES.items()
            for text in texts
        )
    )
    rows = ["brand,us_size,length_mm_min,length_mm_max,sizing_note"]
    for i in range(9):  # 7.0 .. 11.0
        size = 7 + i * 0.5
        mid = reference_mid_mm(size)
        rows.append(f"Volumental,{size:.1f},{mid - 2.1:.1f},{mid + 2.1:.1f},")
        # Acme runs small: each size fits a foot ~4 mm shorter than the reference.
        rows.append(f"Acme,{size:.1f},{mid - 6.1:.1f},{mid - 1.9:.1f},runs small")
    (seed / "size_charts.csv").write_text("\n".join(rows) + "\n")


def write_fake_feed(path: Path) -> None:
    lines = ["retailer,sku,brand,title,us_size,width,price_usd,in_stock,url"]
    for b, m, v, *_rest in FAKE_SHOES:
        widths = _rest[2].split("|") if _rest[2] != "TODO" else ["standard"]
        for i in range(9):
            size = f"{7 + i * 0.5:.1f}"
            for w in widths:
                for store, price in (("Store X", _rest[-1]), ("Store Y", "99")):
                    slug = f"{b}-{m}-{v}".lower()
                    lines.append(
                        f"{store},{store[-1]}-{slug}-{size}-{w},{b},{b} {m} {v} Running Shoe,"
                        f"{size},{w},{price},true,"
                        f"https://example.com/{store[-1].lower()}/{slug}?size={size}&width={w}"
                    )
    path.write_text("\n".join(lines) + "\n")


@pytest.fixture(params=["chroma", "pgvector"])
def backend(request, monkeypatch) -> str:
    monkeypatch.setattr(get_settings(), "vector_backend", request.param)
    return request.param


@pytest.fixture
def store(backend, tmp_path):
    from app.retrieval.store import get_store
    from tests.fakes import KeywordEmbeddings

    return get_store(KeywordEmbeddings(), persist_directory=str(tmp_path / "chroma"))


@pytest.fixture
def catalog(db_session, tmp_path):
    """Fake catalog + size charts + offers loaded into the test DB."""
    from app.db.models import Shoe
    from app.ingest.load_catalog import load_catalog
    from app.ingest.load_offers import load_offers

    write_fake_seed(tmp_path / "fake_seed")
    write_fake_feed(tmp_path / "feed.csv")
    load_catalog(db_session, tmp_path / "fake_seed")
    load_offers(db_session, tmp_path / "feed.csv")
    return {s.model: s.id for s in db_session.scalars(select(Shoe))}


@pytest.fixture
def indexed(catalog, db_session, store):
    """Catalog plus its fit notes embedded in the store under test."""
    from app.ingest.embed_fit_notes import embed_fit_notes

    embed_fit_notes(db_session, store)
    return catalog
