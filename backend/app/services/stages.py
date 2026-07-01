from datetime import date
from uuid import uuid4

from sqlalchemy.orm import Session

from app.constants import DEFAULT_PROJECT_STAGES
from app.models import ProjectStage


def normalize_stage_value(value: str | None) -> str:
    if not value:
        return f"stage_{uuid4().hex[:10]}"
    normalized = "".join(char if char.isalnum() or char == "_" else "_" for char in value.lower())
    return normalized[:80] or f"stage_{uuid4().hex[:10]}"


def ensure_project_stages(db: Session, project_id: int) -> list[ProjectStage]:
    stages = (
        db.query(ProjectStage)
        .filter(ProjectStage.project_id == project_id)
        .order_by(ProjectStage.sort_order.asc(), ProjectStage.id.asc())
        .all()
    )
    if stages:
        return stages

    today = date.today()
    stages = []
    for index, stage in enumerate(DEFAULT_PROJECT_STAGES):
        project_stage = ProjectStage(
            project_id=project_id,
            value=stage["value"],
            label=stage["label"],
            planned_days=stage["planned_days"],
            sort_order=index,
            started_at=today if index == 0 else None,
        )
        db.add(project_stage)
        stages.append(project_stage)
    return stages

