import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from langchain_core.vectorstores import VectorStore
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_recommender, get_session, get_session_factory, get_store
from app.api.routes.users import get_user
from app.api.schemas import TaskOut
from app.db.models import Task

log = logging.getLogger(__name__)
router = APIRouter(tags=["recommend"])
SessionDep = Annotated[Session, Depends(get_session)]


def run_task(
    task_id: uuid.UUID, session_factory: sessionmaker, recommender, store: VectorStore
) -> None:
    with session_factory() as session:
        task = session.get(Task, task_id)
        task.status = "running"
        session.commit()
        try:
            rec = recommender(session, task.user_id, store)
        except Exception as e:
            log.exception("recommendation task %s failed", task_id)
            session.rollback()
            task.status, task.error = "failed", f"{type(e).__name__}: {e}"
        else:
            task.status, task.result = "done", rec.model_dump(mode="json")
        session.commit()


def task_out(task: Task) -> TaskOut:
    return TaskOut(task_id=task.id, status=task.status, result=task.result, error=task.error)


@router.post("/users/{user_id}/recommend", status_code=status.HTTP_202_ACCEPTED)
def start_recommendation(
    user_id: uuid.UUID,
    background: BackgroundTasks,
    session: SessionDep,
    session_factory: Annotated[sessionmaker, Depends(get_session_factory)],
    recommender: Annotated[object, Depends(get_recommender)],
    store: Annotated[VectorStore, Depends(get_store)],
) -> TaskOut:
    """Start the agent in the background. Poll GET /tasks/{task_id} for the result."""
    user = get_user(session, user_id)
    if user.foot_profile is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "confirm a foot profile first (PUT /users/{id}/profile)"
        )
    task = Task(user_id=user_id, status="queued")
    session.add(task)
    session.commit()
    background.add_task(run_task, task.id, session_factory, recommender, store)
    return task_out(task)


@router.get("/tasks/{task_id}")
def read_task(task_id: uuid.UUID, session: SessionDep) -> TaskOut:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "task not found")
    return task_out(task)
