from fastapi import APIRouter, HTTPException, status
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession, require_project_member
from app.models import Attachment, ExpenseRecord
from app.schemas import ExpenseCreate, ExpenseRead, ExpenseUpdate
from app.services.activity import log_activity

router = APIRouter(prefix="/projects/{project_id}/expenses", tags=["expenses"])


def _validate_attachment(db: DbSession, project_id: int, attachment_id: int | None) -> None:
    if attachment_id is None:
        return
    attachment = db.get(Attachment, attachment_id)
    if not attachment or attachment.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="附件不存在或不属于该项目")


@router.get("", response_model=list[ExpenseRead])
def list_expenses(project_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    return (
        db.query(ExpenseRecord)
        .options(joinedload(ExpenseRecord.attachment))
        .filter(ExpenseRecord.project_id == project_id)
        .order_by(ExpenseRecord.created_at.desc())
        .all()
    )


@router.post("", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
def create_expense(project_id: int, payload: ExpenseCreate, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    _validate_attachment(db, project_id, payload.attachment_id)
    record = ExpenseRecord(project_id=project_id, **payload.model_dump())
    db.add(record)
    db.flush()
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="create",
        target_type="expense",
        target_id=record.id,
        message=f"新增记账：{record.sub_item} {record.amount}",
    )
    db.commit()
    db.refresh(record)
    return record


@router.patch("/{expense_id}", response_model=ExpenseRead)
def update_expense(
    project_id: int,
    expense_id: int,
    payload: ExpenseUpdate,
    db: DbSession,
    user: CurrentUser,
):
    require_project_member(db, project_id, user)
    record = db.get(ExpenseRecord, expense_id)
    if not record or record.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记账记录不存在")
    data = payload.model_dump(exclude_unset=True)
    _validate_attachment(db, project_id, data.get("attachment_id"))
    for field, value in data.items():
        setattr(record, field, value)
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="update",
        target_type="expense",
        target_id=record.id,
        message=f"编辑记账：{record.sub_item}",
    )
    db.commit()
    db.refresh(record)
    return record


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(project_id: int, expense_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    record = db.get(ExpenseRecord, expense_id)
    if not record or record.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="记账记录不存在")
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="delete",
        target_type="expense",
        target_id=record.id,
        message=f"删除记账：{record.sub_item}",
    )
    db.delete(record)
    db.commit()
    return None
