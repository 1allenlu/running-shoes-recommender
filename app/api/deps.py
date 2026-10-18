"""FastAPI dependencies. Tests override these to swap in fakes."""

from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from langchain_core.vectorstores import VectorStore
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import SessionLocal, get_session  # noqa: F401  (re-exported)
from app.schemas.foot_profile import FootProfile

ScanParser = Callable[[list[Path]], FootProfile]


def get_session_factory() -> sessionmaker[Session]:
    """For background tasks, which outlive the request's session."""
    return SessionLocal


@lru_cache
def get_store() -> VectorStore:
    from app.retrieval.store import get_store as build_store

    return build_store()


def get_scan_parser() -> ScanParser:
    from app.parsing.scan_parser import parse_scan

    return parse_scan


def get_recommender():
    from app.agent.recommender import run_recommendation

    return run_recommendation
