from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.models import InspectionChecklist, StageTask
from app.services.stages import ensure_project_stages
from app.services.inspection_templates import INSPECTION_TEMPLATES
from app.services.stage_task_templates import STAGE_TASK_TEMPLATES


def _allowed_stage_values(db: Session, project_id: int) -> set[str]:
    stages = ensure_project_stages(db, project_id)
    db.flush()
    return {stage.value for stage in stages}


def _filter_templates(
    templates: dict[str, list[dict[str, str]]],
    allowed_stages: Iterable[str],
) -> Iterable[tuple[str, dict[str, str]]]:
    allowed = set(allowed_stages)
    for stage, items in templates.items():
        if stage not in allowed:
            continue
        for item in items:
            yield stage, item


def ensure_stage_task_templates(db: Session, project_id: int) -> int:
    exists = db.query(StageTask.id).filter(StageTask.project_id == project_id).first()
    if exists:
        return 0

    created = 0
    for stage, item in _filter_templates(STAGE_TASK_TEMPLATES, _allowed_stage_values(db, project_id)):
        db.add(
            StageTask(
                project_id=project_id,
                stage=stage,
                title=item["title"],
                description=item["description"],
            )
        )
        created += 1
    return created


def ensure_inspection_templates(db: Session, project_id: int) -> int:
    exists = (
        db.query(InspectionChecklist.id)
        .filter(InspectionChecklist.project_id == project_id)
        .first()
    )
    if exists:
        return 0

    created = 0
    for stage, item in _filter_templates(INSPECTION_TEMPLATES, _allowed_stage_values(db, project_id)):
        db.add(
            InspectionChecklist(
                project_id=project_id,
                stage=stage,
                item=item["item"],
                standard=item["standard"],
            )
        )
        created += 1
    return created
