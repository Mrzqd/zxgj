from fastapi import APIRouter, HTTPException, status
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession, require_project_member, require_project_owner
from app.models import Project, ProjectMember, ProjectRole, User
from app.schemas import MemberInvite, ProjectCreate, ProjectMemberRead, ProjectRead, ProjectUpdate
from app.services.activity import log_activity
from app.services.stages import ensure_project_stages

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
def list_projects(db: DbSession, user: CurrentUser):
    return (
        db.query(Project)
        .join(ProjectMember)
        .filter(ProjectMember.user_id == user.id)
        .order_by(Project.created_at.desc())
        .all()
    )


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: DbSession, user: CurrentUser):
    project = Project(name=payload.name, address=payload.address, notes=payload.notes, owner_id=user.id)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role=ProjectRole.owner.value))
    ensure_project_stages(db, project.id)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    return project


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, db: DbSession, user: CurrentUser):
    require_project_owner(db, project_id, user)
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}/members", response_model=list[ProjectMemberRead])
def list_members(project_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    return (
        db.query(ProjectMember)
        .options(joinedload(ProjectMember.user))
        .filter(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.created_at.asc())
        .all()
    )


@router.post("/{project_id}/members", response_model=ProjectMemberRead, status_code=status.HTTP_201_CREATED)
def invite_member(project_id: int, payload: MemberInvite, db: DbSession, user: CurrentUser):
    require_project_owner(db, project_id, user)
    invitee = db.query(User).filter(User.email == payload.email.lower()).first()
    if invitee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="该邮箱尚未注册")
    existing = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == invitee.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该用户已在项目中")
    role = payload.role if payload.role in {ProjectRole.owner.value, ProjectRole.editor.value} else "editor"
    member = ProjectMember(project_id=project_id, user_id=invitee.id, role=role)
    db.add(member)
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="invite",
        target_type="member",
        target_id=invitee.id,
        message=f"邀请成员：{invitee.name}",
    )
    db.commit()
    db.refresh(member)
    return (
        db.query(ProjectMember)
        .options(joinedload(ProjectMember.user))
        .filter(ProjectMember.id == member.id)
        .one()
    )
