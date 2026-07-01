from sqlalchemy.orm import Session

from app.models import ActivityLog, User


def log_activity(
    db: Session,
    *,
    project_id: int,
    actor: User,
    action: str,
    target_type: str,
    message: str,
    target_id: int | None = None,
) -> None:
    db.add(
        ActivityLog(
            project_id=project_id,
            actor_id=actor.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            message=message[:255],
        )
    )

