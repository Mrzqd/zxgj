from fastapi import APIRouter, HTTPException, status
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession, require_project_member
from app.models import Attachment, InspectionChecklist
from app.schemas import InspectionCreate, InspectionRead, InspectionUpdate
from app.services.activity import log_activity
from app.services.templates import ensure_inspection_templates

router = APIRouter(prefix="/projects/{project_id}/inspections", tags=["inspections"])


def _validate_attachment(db: DbSession, project_id: int, attachment_id: int | None) -> None:
    if attachment_id is None:
        return
    attachment = db.get(Attachment, attachment_id)
    if not attachment or attachment.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="附件不存在或不属于该项目")


@router.get("", response_model=list[InspectionRead])
def list_inspections(project_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    if ensure_inspection_templates(db, project_id):
        db.commit()
    return (
        db.query(InspectionChecklist)
        .options(joinedload(InspectionChecklist.attachment))
        .filter(InspectionChecklist.project_id == project_id)
        .order_by(InspectionChecklist.created_at.desc())
        .all()
    )


@router.post("", response_model=InspectionRead, status_code=status.HTTP_201_CREATED)
def create_inspection(project_id: int, payload: InspectionCreate, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    _validate_attachment(db, project_id, payload.attachment_id)
    inspection = InspectionChecklist(project_id=project_id, **payload.model_dump())
    db.add(inspection)
    db.flush()
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="create",
        target_type="inspection",
        target_id=inspection.id,
        message=f"新增验收项：{inspection.item}",
    )
    db.commit()
    db.refresh(inspection)
    return inspection


@router.patch("/{inspection_id}", response_model=InspectionRead)
def update_inspection(
    project_id: int,
    inspection_id: int,
    payload: InspectionUpdate,
    db: DbSession,
    user: CurrentUser,
):
    require_project_member(db, project_id, user)
    inspection = db.get(InspectionChecklist, inspection_id)
    if not inspection or inspection.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="验收项不存在")
    data = payload.model_dump(exclude_unset=True)
    _validate_attachment(db, project_id, data.get("attachment_id"))
    for field, value in data.items():
        setattr(inspection, field, value)
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="update",
        target_type="inspection",
        target_id=inspection.id,
        message=f"更新验收项：{inspection.item}",
    )
    db.commit()
    db.refresh(inspection)
    return inspection


@router.delete("/{inspection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inspection(project_id: int, inspection_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    inspection = db.get(InspectionChecklist, inspection_id)
    if not inspection or inspection.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="验收项不存在")
    db.delete(inspection)
    db.commit()
    return None
