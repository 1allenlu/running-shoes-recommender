import tempfile
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import ScanParser, get_scan_parser, get_session
from app.api.schemas import FeedbackIn, FeedbackOut, ScanOut, UserOut
from app.db.models import Feedback, Shoe, User
from app.parsing.scan_parser import PARSER_VERSION, content_block, save_scan
from app.schemas.foot_profile import FootProfile
from app.schemas.questionnaire import Questionnaire

router = APIRouter(prefix="/users", tags=["users"])
SessionDep = Annotated[Session, Depends(get_session)]


def get_user(session: Session, user_id: uuid.UUID) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return user


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(session: SessionDep) -> UserOut:
    user = User()
    session.add(user)
    session.commit()
    return UserOut.model_validate(user)


@router.get("/{user_id}")
def read_user(user_id: uuid.UUID, session: SessionDep) -> UserOut:
    return UserOut.model_validate(get_user(session, user_id))


@router.post("/{user_id}/scans", status_code=status.HTTP_201_CREATED)
def upload_scan(
    user_id: uuid.UUID,
    files: list[UploadFile],
    session: SessionDep,
    parse: Annotated[ScanParser, Depends(get_scan_parser)],
) -> ScanOut:
    """Upload report screenshots or the PDF. Returns the parsed profile for the runner to
    confirm; it is not saved to the profile until PUT /users/{id}/profile."""
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
    return ScanOut(scan_id=scan.id, parser_version=PARSER_VERSION, parsed_profile=profile)


@router.put("/{user_id}/profile")
def confirm_profile(user_id: uuid.UUID, profile: FootProfile, session: SessionDep) -> UserOut:
    user = get_user(session, user_id)
    user.foot_profile = profile.model_dump(mode="json")
    session.commit()
    return UserOut.model_validate(user)


@router.put("/{user_id}/questionnaire")
def save_questionnaire(
    user_id: uuid.UUID, questionnaire: Questionnaire, session: SessionDep
) -> UserOut:
    user = get_user(session, user_id)
    user.questionnaire = questionnaire.model_dump(mode="json")
    session.commit()
    return UserOut.model_validate(user)


@router.post("/{user_id}/feedback", status_code=status.HTTP_201_CREATED)
def add_feedback(user_id: uuid.UUID, body: FeedbackIn, session: SessionDep) -> FeedbackOut:
    get_user(session, user_id)
    if session.get(Shoe, body.shoe_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "shoe not found")
    feedback = Feedback(user_id=user_id, **body.model_dump())
    session.add(feedback)
    session.commit()
    return FeedbackOut(id=feedback.id, created_at=feedback.created_at, **body.model_dump())
