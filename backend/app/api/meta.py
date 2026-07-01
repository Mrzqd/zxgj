from fastapi import APIRouter

from app.constants import AMOUNT_CATEGORIES, INSPECTION_STATUSES, RENOVATION_STAGES, TASK_STATUSES

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/options")
def get_options():
    return {
        "renovation_stages": RENOVATION_STAGES,
        "amount_categories": AMOUNT_CATEGORIES,
        "task_statuses": TASK_STATUSES,
        "inspection_statuses": INSPECTION_STATUSES,
    }

