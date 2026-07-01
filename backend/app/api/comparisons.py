from fastapi import APIRouter, HTTPException, status
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession, require_project_member
from app.models import Attachment, ComparisonItem, ComparisonQuote
from app.schemas import (
    ComparisonItemCreate,
    ComparisonItemRead,
    ComparisonItemUpdate,
    ComparisonQuoteCreate,
    ComparisonQuoteRead,
    ComparisonQuoteUpdate,
)
from app.services.activity import log_activity

router = APIRouter(prefix="/projects/{project_id}/comparisons", tags=["comparisons"])


def _get_item(db: DbSession, project_id: int, item_id: int) -> ComparisonItem:
    item = db.get(ComparisonItem, item_id)
    if not item or item.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="比价物品不存在")
    return item


def _validate_attachment(db: DbSession, project_id: int, attachment_id: int | None) -> None:
    if attachment_id is None:
        return
    attachment = db.get(Attachment, attachment_id)
    if not attachment or attachment.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="截图不存在或不属于该项目")


@router.get("", response_model=list[ComparisonItemRead])
def list_comparisons(project_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    return (
        db.query(ComparisonItem)
        .options(joinedload(ComparisonItem.quotes).joinedload(ComparisonQuote.screenshot))
        .filter(ComparisonItem.project_id == project_id)
        .order_by(ComparisonItem.created_at.desc())
        .all()
    )


@router.post("", response_model=ComparisonItemRead, status_code=status.HTTP_201_CREATED)
def create_comparison_item(project_id: int, payload: ComparisonItemCreate, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    item = ComparisonItem(project_id=project_id, **payload.model_dump())
    db.add(item)
    db.flush()
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="create",
        target_type="comparison_item",
        target_id=item.id,
        message=f"新增比价物品：{item.space}-{item.name}",
    )
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comparison_item(project_id: int, item_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    item = _get_item(db, project_id, item_id)
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="delete",
        target_type="comparison_item",
        target_id=item.id,
        message=f"删除比价物品：{item.space}-{item.name}",
    )
    db.delete(item)
    db.commit()
    return None


@router.patch("/{item_id}", response_model=ComparisonItemRead)
def update_comparison_item(
    project_id: int,
    item_id: int,
    payload: ComparisonItemUpdate,
    db: DbSession,
    user: CurrentUser,
):
    require_project_member(db, project_id, user)
    item = _get_item(db, project_id, item_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="update",
        target_type="comparison_item",
        target_id=item.id,
        message=f"编辑比价物品：{item.space}-{item.name}",
    )
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/quotes", response_model=ComparisonQuoteRead, status_code=status.HTTP_201_CREATED)
def create_quote(
    project_id: int,
    item_id: int,
    payload: ComparisonQuoteCreate,
    db: DbSession,
    user: CurrentUser,
):
    require_project_member(db, project_id, user)
    _get_item(db, project_id, item_id)
    _validate_attachment(db, project_id, payload.screenshot_attachment_id)
    quote = ComparisonQuote(item_id=item_id, **payload.model_dump())
    db.add(quote)
    db.flush()
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="create",
        target_type="comparison_quote",
        target_id=quote.id,
        message=f"新增报价：{quote.vendor} {quote.price}",
    )
    db.commit()
    db.refresh(quote)
    return quote


@router.patch("/{item_id}/quotes/{quote_id}", response_model=ComparisonQuoteRead)
def update_quote(
    project_id: int,
    item_id: int,
    quote_id: int,
    payload: ComparisonQuoteUpdate,
    db: DbSession,
    user: CurrentUser,
):
    require_project_member(db, project_id, user)
    _get_item(db, project_id, item_id)
    quote = db.get(ComparisonQuote, quote_id)
    if not quote or quote.item_id != item_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报价不存在")
    data = payload.model_dump(exclude_unset=True)
    _validate_attachment(db, project_id, data.get("screenshot_attachment_id"))
    for field, value in data.items():
        setattr(quote, field, value)
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="update",
        target_type="comparison_quote",
        target_id=quote.id,
        message=f"编辑报价：{quote.vendor} {quote.price}",
    )
    db.commit()
    db.refresh(quote)
    return quote


@router.delete("/{item_id}/quotes/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quote(project_id: int, item_id: int, quote_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    _get_item(db, project_id, item_id)
    quote = db.get(ComparisonQuote, quote_id)
    if not quote or quote.item_id != item_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="报价不存在")
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="delete",
        target_type="comparison_quote",
        target_id=quote.id,
        message=f"删除报价：{quote.vendor}",
    )
    db.delete(quote)
    db.commit()
    return None
