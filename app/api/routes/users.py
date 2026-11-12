import tempfile
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import ScanParser, get_scan_parser, get_session
from app.api.schemas import FeedbackIn, FeedbackOut, HistoryOut, ScanOut, UserOut
from app.db.models import Feedback, Recommendation, Scan, Shoe, ShoeHistory, User
from app.db.models import Preferences as PreferencesRow
from app.parsing.scan_parser import content_block, save_scan
from app.recommend import confirmed_profile, preferences, resolve_shoe_id
from app.schemas.foot_profile import FootProfile
from app.schemas.preferences import HistoryEntry, Preferences

router = APIRouter(prefix="/users", tags=["users"])
SessionDep = Annotated[Session, Depends(get_session)]
MANUAL_ENTRY = "manual"


def get_user(session: Session, user_id: uuid.UUID) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return user


def user_out(session: Session, user: User) -> UserOut:
    rows = session.scalars(
        select(ShoeHistory).where(ShoeHistory.user_id == user.id).order_by(ShoeHistory.id)
    )
    return UserOut(
        id=user.id,
        created_at=user.created_at,
        confirmed_profile=confirmed_profile(session, user.id),
        preferences=preferences(session, user.id) if session.get(PreferencesRow, user.id) else None,
        history=[_history_out(h) for h in rows],
    )


def scan_out(scan: Scan) -> ScanOut:
    return ScanOut(
        scan_id=scan.id,
        parser_version=scan.parser_version,
        parsed_profile=scan.parsed_profile,
        confirmed_profile=scan.confirmed_profile,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(session: SessionDep) -> UserOut:
    user = User()
    session.add(user)
    session.commit()
    return user_out(session, user)


@router.get("/{user_id}")
def read_user(user_id: uuid.UUID, session: SessionDep) -> UserOut:
    return user_out(session, get_user(session, user_id))


# --- Scans --------------------------------------------------------------------------------


@router.post("/{user_id}/scans", status_code=status.HTTP_201_CREATED)
def upload_scan(
    user_id: uuid.UUID,
    files: list[UploadFile],
    session: SessionDep,
    parse: Annotated[ScanParser, Depends(get_scan_parser)],
) -> ScanOut:
    """Upload report screenshots or the PDF. Returns the parsed profile for the runner to
    check; only a confirmed profile (PUT .../confirm) is used for ranking."""
    get_user(session, user_id)
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i, upload in enumerate(files):
            path = Path(tmp) / f"{i:02d}_{Path(upload.filename or 'report').name}"
            path.write_bytes(upload.file.read())
            paths.append(path)
        try:
            for path in paths:
                content_block(path)  # validates the file type before calling the LLM
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
        try:
            profile = parse(paths)
        except Exception as e:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                f"Couldn't read the report ({type(e).__name__}: {e})",
            ) from e
        scan = save_scan(session, user_id, paths, profile)
    return scan_out(scan)


@router.post("/{user_id}/scans/manual", status_code=status.HTTP_201_CREATED)
def enter_scan_by_hand(user_id: uuid.UUID, profile: FootProfile, session: SessionDep) -> ScanOut:
    """For runners typing in their report: saved as already confirmed."""
    get_user(session, user_id)
    scan = Scan(
        user_id=user_id,
        parser_version=MANUAL_ENTRY,
        confirmed_profile=profile.model_dump(mode="json"),
    )
    session.add(scan)
    session.commit()
    return scan_out(scan)


@router.put("/{user_id}/scans/{scan_id}/confirm")
def confirm_scan(
    user_id: uuid.UUID, scan_id: int, profile: FootProfile, session: SessionDep
) -> ScanOut:
    """Save the confirmed (possibly corrected) profile."""
    scan = session.get(Scan, scan_id)
    if scan is None or scan.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scan not found")
    scan.confirmed_profile = profile.model_dump(mode="json")
    session.commit()
    return scan_out(scan)


# --- Preferences and history --------------------------------------------------------------


@router.put("/{user_id}/preferences")
def save_preferences(user_id: uuid.UUID, prefs: Preferences, session: SessionDep) -> Preferences:
    get_user(session, user_id)
    row = session.get(PreferencesRow, user_id) or PreferencesRow(user_id=user_id)
    for key, value in prefs.model_dump().items():
        setattr(row, key, value)
    session.add(row)
    session.commit()
    return prefs


def _history_out(h: ShoeHistory) -> HistoryOut:
    return HistoryOut(
        id=h.id,
        shoe_id=h.shoe_id,
        raw_name=h.raw_name,
        us_size=None if h.us_size is None else float(h.us_size),
        width=h.width,
        rating=h.rating,
        issues=h.issues,
    )


def _add_history(session: Session, user_id: uuid.UUID, entries: list[HistoryEntry]) -> list:
    rows = []
    for entry in entries:
        data = entry.model_dump()
        if data["shoe_id"] is None:
            data["shoe_id"] = resolve_shoe_id(session, entry.raw_name)
        elif session.get(Shoe, data["shoe_id"]) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"shoe {data['shoe_id']} not found")
        rows.append(ShoeHistory(user_id=user_id, **data))
    session.add_all(rows)
    session.commit()
    return [_history_out(r) for r in rows]


@router.post("/{user_id}/history", status_code=status.HTTP_201_CREATED)
def add_history(
    user_id: uuid.UUID, entries: list[HistoryEntry], session: SessionDep
) -> list[HistoryOut]:
    """Add shoes the runner has run in, each rated loved / fine / hated with issue tags."""
    get_user(session, user_id)
    return _add_history(session, user_id, entries)


@router.put("/{user_id}/history")
def replace_history(
    user_id: uuid.UUID, entries: list[HistoryEntry], session: SessionDep
) -> list[HistoryOut]:
    """Replace the runner's whole shoe history (what the history screen sends)."""
    get_user(session, user_id)
    session.execute(delete(ShoeHistory).where(ShoeHistory.user_id == user_id))
    return _add_history(session, user_id, entries)


# --- Feedback -----------------------------------------------------------------------------


@router.post("/{user_id}/feedback", status_code=status.HTTP_201_CREATED)
def add_feedback(user_id: uuid.UUID, body: FeedbackIn, session: SessionDep) -> FeedbackOut:
    """How a recommended shoe worked out. The next recommendation uses it like history."""
    get_user(session, user_id)
    if session.get(Shoe, body.shoe_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "shoe not found")
    if body.recommendation_id is not None:
        rec = session.get(Recommendation, body.recommendation_id)
        if rec is None or rec.user_id != user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "recommendation not found")
    feedback = Feedback(user_id=user_id, **body.model_dump())
    session.add(feedback)
    session.commit()
    return FeedbackOut(id=feedback.id, created_at=feedback.created_at, **body.model_dump())
