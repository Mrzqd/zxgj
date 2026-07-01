from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession, require_project_member
from app.models import ProjectProgress, ProjectStage
from app.schemas import ProjectStageCreate, ProjectStageRead, ProjectStageUpdate
from app.services.activity import log_activity
from app.services.stages import ensure_project_stages, normalize_stage_value

router = APIRouter(prefix="/projects/{project_id}/stages", tags=["stages"])


@router.get("", response_model=list[ProjectStageRead])
def list_project_stages(project_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    stages = ensure_project_stages(db, project_id)
    db.commit()
    return (
        db.query(ProjectStage)
        .filter(ProjectStage.project_id == project_id)
        .order_by(ProjectStage.sort_order.asc(), ProjectStage.id.asc())
        .all()
    )


@router.post("", response_model=ProjectStageRead, status_code=status.HTTP_201_CREATED)
def create_project_stage(project_id: int, payload: ProjectStageCreate, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    ensure_project_stages(db, project_id)
    value = normalize_stage_value(payload.value)
    existing = (
        db.query(ProjectStage)
        .filter(ProjectStage.project_id == project_id, ProjectStage.value == value)
        .first()
    )
    if existing:
        value = normalize_stage_value(None)
    max_order = (
        db.query(ProjectStage)
        .filter(ProjectStage.project_id == project_id)
        .order_by(ProjectStage.sort_order.desc())
        .first()
    )
    stage = ProjectStage(
        project_id=project_id,
        value=value,
        label=payload.label,
        planned_days=payload.planned_days,
        sort_order=payload.sort_order if payload.sort_order is not None else (max_order.sort_order + 1 if max_order else 0),
        started_at=payload.started_at,
        completed_at=payload.completed_at,
    )
    db.add(stage)
    db.flush()
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="create",
        target_type="project_stage",
        target_id=stage.id,
        message=f"新增装修阶段：{stage.label}",
    )
    db.commit()
    db.refresh(stage)
    return stage


@router.patch("/{stage_id}", response_model=ProjectStageRead)
def update_project_stage(
    project_id: int,
    stage_id: int,
    payload: ProjectStageUpdate,
    db: DbSession,
    user: CurrentUser,
):
    require_project_member(db, project_id, user)
    stage = db.get(ProjectStage, stage_id)
    if not stage or stage.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="装修阶段不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(stage, field, value)
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="update",
        target_type="project_stage",
        target_id=stage.id,
        message=f"编辑装修阶段：{stage.label}",
    )
    db.commit()
    db.refresh(stage)
    return stage


@router.delete("/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_stage(project_id: int, stage_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    stage = db.get(ProjectStage, stage_id)
    if not stage or stage.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="装修阶段不存在")
    progress = db.query(ProjectProgress).filter(ProjectProgress.project_id == project_id).first()
    if progress and progress.current_stage == stage.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前进度阶段不能删除，请先切换进度")
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="delete",
        target_type="project_stage",
        target_id=stage.id,
        message=f"删除装修阶段：{stage.label}",
    )
    db.delete(stage)
    db.commit()
    return None

