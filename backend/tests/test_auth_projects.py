import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["EMBEDDING_DIMENSIONS"] = "384"
os.environ["RERANK_PROVIDER"] = "none"
os.environ["LLM_PROVIDER"] = "none"

from app.api.auth import register
from app.api.projects import accept_invite_link, create_invite_link, create_project, list_projects
from app.db.session import Base, SessionLocal, engine
from app.models import ProjectInviteLink
from app.schemas import ProjectCreate, ProjectInviteLinkCreate, UserCreate


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


def test_project_invite_link_accept_limit_and_expiry():
    db = SessionLocal()
    try:
        owner_token = register(
            UserCreate(email="owner@example.com", name="屋主", password="password123"),
            db,
        )
        first_invitee_token = register(
            UserCreate(email="first@example.com", name="成员一", password="password123"),
            db,
        )
        second_invitee_token = register(
            UserCreate(email="second@example.com", name="成员二", password="password123"),
            db,
        )
        project = create_project(
            ProjectCreate(name="新家装修", address="杭州", notes=None),
            db,
            owner_token.user,
        )

        invite = create_invite_link(
            project.id,
            ProjectInviteLinkCreate(expires_in_hours=24, max_accepts=1),
            db,
            owner_token.user,
        )
        member = accept_invite_link(invite.token, db, first_invitee_token.user)

        assert member.project_id == project.id
        assert member.user.email == "first@example.com"
        stored_invite = db.get(ProjectInviteLink, invite.id)
        assert stored_invite is not None
        assert stored_invite.accepted_count == 1

        try:
            accept_invite_link(invite.token, db, second_invitee_token.user)
        except Exception as exc:
            assert getattr(exc, "status_code") == 410
            assert "次数" in exc.detail
        else:
            raise AssertionError("exhausted invite should fail")

        expired_invite = create_invite_link(
            project.id,
            ProjectInviteLinkCreate(expires_in_hours=1, max_accepts=5),
            db,
            owner_token.user,
        )
        stored_expired_invite = db.get(ProjectInviteLink, expired_invite.id)
        assert stored_expired_invite is not None
        stored_expired_invite.expires_at = stored_expired_invite.created_at
        db.commit()

        try:
            accept_invite_link(expired_invite.token, db, second_invitee_token.user)
        except Exception as exc:
            assert getattr(exc, "status_code") == 410
            assert "过期" in exc.detail
        else:
            raise AssertionError("expired invite should fail")
    finally:
        db.close()
