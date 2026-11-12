"""FastAPI dependencies. Tests override these to swap in fakes."""

from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.db.session import SessionLocal, get_session  # noqa: F401  (re-exported)
from app.schemas.foot_profile import FootProfile

ScanParser = Callable[[list[Path]], FootProfile]


def get_session_factory() -> sessionmaker[Session]:
    """For background tasks, which outlive the request's session."""
    return SessionLocal


def get_scan_parser() -> ScanParser:
    from app.parsing.scan_parser import parse_scan

    return parse_scan
