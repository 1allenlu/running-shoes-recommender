import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_session, get_session_factory
from app.api.routes.users import get_user
from app.api.schemas import TaskOut
from app.db.models import Recommendation
from app.recommend import build_recommendation, confirmed_profile

log = logging.getLogger(__name__)
router = APIRouter(tags=["recommend"])
SessionDep = Annotated[Session, Depends(get_session)]


def run_task(rec_id: uuid.UUID, session_factory: sessionmaker) -> None:
    with session_factory() as session:
        row = session.get(Recommendation, rec_id)
        row.task_status = "running"
        session.commit()
        try:
            rec, ranking = build_recommendation(session, row.user_id)
        except Exception as e:
            log.exception("recommendation %s failed", rec_id)
            session.rollback()
            row.task_status, row.error = "failed", f"{type(e).__name__}: {e}"
        else:
            row.task_status = "done"
            row.ranker_version = ranking.ranker_version
            row.candidates = [c.model_dump(mode="json") for c in ranking.candidates]
            row.result = rec.model_dump(mode="json")
        session.commit()


def task_out(row: Recommendation) -> TaskOut:
    return TaskOut(task_id=row.id, status=row.task_status, result=row.result, error=row.error)


@router.post("/users/{user_id}/recommend", status_code=status.HTTP_202_ACCEPTED)
def start_recommendation(
    user_id: uuid.UUID,
    background: BackgroundTasks,
    session: SessionDep,
    session_factory: Annotated[sessionmaker, Depends(get_session_factory)],
) -> TaskOut:
    """Rank shoes in the background. Poll GET /tasks/{task_id} for the result."""
    get_user(session, user_id)
    if confirmed_profile(session, user_id) is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "confirm a foot profile first (PUT /users/{id}/scans/{scan_id}/confirm)",
        )
    row = Recommendation(user_id=user_id, task_status="queued")
    session.add(row)
    session.commit()
    background.add_task(run_task, row.id, session_factory)
    return task_out(row)


@router.get("/tasks/{task_id}")
def read_task(task_id: uuid.UUID, session: SessionDep) -> TaskOut:
    row = session.get(Recommendation, task_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "task not found")
    return task_out(row)
