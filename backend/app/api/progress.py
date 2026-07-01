from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, require_project_member
from app.models import ProjectProgress
from app.schemas import ProjectProgressRead, ProjectProgressUpdate
from app.services.activity import log_activity
from app.services.stages import ensure_project_stages

router = APIRouter(prefix="/projects/{project_id}/progress", tags=["progress"])


def _get_or_create_progress(db: DbSession, project_id: int) -> ProjectProgress:
    progress = db.query(ProjectProgress).filter(ProjectProgress.project_id == project_id).first()
    if progress is None:
        stages = ensure_project_stages(db, project_id)
        progress = ProjectProgress(project_id=project_id, current_stage=stages[0].value if stages else "design")
        db.add(progress)
        db.commit()
        db.refresh(progress)
    return progress


@router.get("", response_model=ProjectProgressRead)
def get_progress(project_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    return _get_or_create_progress(db, project_id)


@router.patch("", response_model=ProjectProgressRead)
def update_progress(project_id: int, payload: ProjectProgressUpdate, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    progress = _get_or_create_progress(db, project_id)
    progress.current_stage = payload.current_stage
    progress.note = payload.note
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="update",
        target_type="progress",
        target_id=progress.id,
        message=f"更新装修进度：{payload.current_stage}",
    )
    db.commit()
    db.refresh(progress)
    return progress
