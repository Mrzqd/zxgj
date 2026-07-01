import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["EMBEDDING_DIMENSIONS"] = "384"
os.environ["RERANK_PROVIDER"] = "none"
os.environ["LLM_PROVIDER"] = "none"

from app.api.auth import register
from app.api.projects import create_project, list_projects
from app.db.session import Base, SessionLocal, engine
from app.schemas import ProjectCreate, UserCreate


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_register_create_project_and_list():
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
        projects = list_projects(db, token.user)

        assert token.access_token
        assert project.name == "新家装修"
        assert len(projects) == 1
        assert projects[0].owner_id == token.user.id
    finally:
        db.close()
