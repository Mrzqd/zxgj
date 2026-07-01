from fastapi import APIRouter
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession, require_project_member
from app.models import ActivityLog
from app.schemas import ActivityLogRead

router = APIRouter(prefix="/projects/{project_id}/activity", tags=["activity"])


@router.get("", response_model=list[ActivityLogRead])
def list_activity(project_id: int, db: DbSession, user: CurrentUser, limit: int = 30):
    require_project_member(db, project_id, user)
    safe_limit = min(max(limit, 1), 100)
    return (
        db.query(ActivityLog)
        .options(joinedload(ActivityLog.actor))
        .filter(ActivityLog.project_id == project_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(safe_limit)
        .all()
    )

