from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession, require_project_member
from app.models import StageTask
from app.schemas import StageTaskCreate, StageTaskRead, StageTaskUpdate
from app.services.activity import log_activity
from app.services.templates import ensure_stage_task_templates

router = APIRouter(prefix="/projects/{project_id}/stage-tasks", tags=["stage-tasks"])


@router.get("", response_model=list[StageTaskRead])
def list_stage_tasks(project_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    if ensure_stage_task_templates(db, project_id):
        db.commit()
    return (
        db.query(StageTask)
        .filter(StageTask.project_id == project_id)
        .order_by(StageTask.due_at.asc().nullslast(), StageTask.created_at.desc())
        .all()
    )


@router.post("", response_model=StageTaskRead, status_code=status.HTTP_201_CREATED)
def create_stage_task(project_id: int, payload: StageTaskCreate, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    task = StageTask(project_id=project_id, **payload.model_dump())
    db.add(task)
    db.flush()
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="create",
        target_type="stage_task",
        target_id=task.id,
        message=f"新增阶段事项：{task.title}",
    )
    db.commit()
    db.refresh(task)
    return task


@router.patch("/{task_id}", response_model=StageTaskRead)
def update_stage_task(
    project_id: int,
    task_id: int,
    payload: StageTaskUpdate,
    db: DbSession,
    user: CurrentUser,
):
    require_project_member(db, project_id, user)
    task = db.get(StageTask, task_id)
    if not task or task.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="阶段事项不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="update",
        target_type="stage_task",
        target_id=task.id,
        message=f"更新阶段事项：{task.title}",
    )
    db.commit()
    db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_stage_task(project_id: int, task_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    task = db.get(StageTask, task_id)
    if not task or task.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="阶段事项不存在")
    db.delete(task)
    db.commit()
    return None
