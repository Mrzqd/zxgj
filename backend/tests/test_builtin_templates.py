import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["EMBEDDING_DIMENSIONS"] = "384"
os.environ["RERANK_PROVIDER"] = "none"
os.environ["LLM_PROVIDER"] = "none"

from app.api.auth import register
from app.api.inspections import list_inspections
from app.api.projects import create_project
from app.api.stage_tasks import list_stage_tasks
from app.db.session import Base, SessionLocal, engine
from app.models import InspectionChecklist, StageTask
from app.schemas import ProjectCreate, UserCreate


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_builtin_templates_seed_empty_project_once():
    db = SessionLocal()
    try:
        token = register(
            UserCreate(email="owner@example.com", name="屋主", password="password123"),
            db,
        )
        project = create_project(
            ProjectCreate(name="新家装修", address="杭州", notes=None),
            db,
            token.user,
        )

        tasks = list_stage_tasks(project.id, db, token.user)
        inspections = list_inspections(project.id, db, token.user)
        second_tasks = list_stage_tasks(project.id, db, token.user)
        second_inspections = list_inspections(project.id, db, token.user)

        assert len(tasks) >= 20
        assert len(inspections) >= 20
        assert len(second_tasks) == len(tasks)
        assert len(second_inspections) == len(inspections)
        assert db.query(StageTask).filter(StageTask.project_id == project.id).count() == len(tasks)
        assert (
            db.query(InspectionChecklist)
            .filter(InspectionChecklist.project_id == project.id)
            .count()
            == len(inspections)
        )
        assert any(task.title == "安排水路打压测试" for task in tasks)
        assert any(item.item == "卫生间流水坡度" for item in inspections)
    finally:
        db.close()
