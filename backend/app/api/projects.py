from datetime import datetime, timedelta, timezone
from secrets import token_urlsafe

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession, require_project_member, require_project_owner
from app.models import Project, ProjectInviteLink, ProjectMember, ProjectRole, User
from app.schemas import (
    MemberInvite,
    ProjectCreate,
    ProjectInviteLinkCreate,
    ProjectInviteLinkRead,
    ProjectMemberRead,
    ProjectRead,
    ProjectUpdate,
)
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


@router.get("/{project_id}/invite-links", response_model=list[ProjectInviteLinkRead])
def list_invite_links(project_id: int, db: DbSession, user: CurrentUser):
    require_project_owner(db, project_id, user)
    return (
        db.query(ProjectInviteLink)
        .filter(ProjectInviteLink.project_id == project_id)
        .order_by(ProjectInviteLink.created_at.desc())
        .limit(20)
        .all()
    )


@router.post(
    "/{project_id}/invite-links",
    response_model=ProjectInviteLinkRead,
    status_code=status.HTTP_201_CREATED,
)
def create_invite_link(project_id: int, payload: ProjectInviteLinkCreate, db: DbSession, user: CurrentUser):
    require_project_owner(db, project_id, user)
    role = payload.role if payload.role in {ProjectRole.owner.value, ProjectRole.editor.value} else ProjectRole.editor.value
    invite = ProjectInviteLink(
        project_id=project_id,
        token=_new_invite_token(db),
        role=role,
        max_accepts=payload.max_accepts,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=payload.expires_in_hours),
        created_by_id=user.id,
    )
    db.add(invite)
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="create_invite_link",
        target_type="invite_link",
        target_id=None,
        message=f"生成邀请链接：{payload.expires_in_hours} 小时有效，最多 {payload.max_accepts} 次接收",
    )
    db.commit()
    db.refresh(invite)
    return invite


@router.post("/invite-links/{invite_token}/accept", response_model=ProjectMemberRead)
def accept_invite_link(invite_token: str, db: DbSession, user: CurrentUser):
    invite = (
        db.query(ProjectInviteLink)
        .filter(ProjectInviteLink.token == invite_token)
        .first()
    )
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="邀请链接不存在")
    if _is_expired(invite):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="邀请链接已过期")
    if invite.accepted_count >= invite.max_accepts:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="邀请链接接收次数已用完")

    existing = (
        db.query(ProjectMember)
        .options(joinedload(ProjectMember.user))
        .filter(ProjectMember.project_id == invite.project_id, ProjectMember.user_id == user.id)
        .first()
    )
    if existing:
        return existing

    invite.accepted_count += 1
    member = ProjectMember(project_id=invite.project_id, user_id=user.id, role=invite.role)
    db.add(member)
    log_activity(
        db,
        project_id=invite.project_id,
        actor=user,
        action="accept_invite",
        target_type="member",
        target_id=user.id,
        message=f"通过邀请链接加入项目：{user.name}",
    )
    db.commit()
    db.refresh(member)
    return (
        db.query(ProjectMember)
        .options(joinedload(ProjectMember.user))
        .filter(ProjectMember.id == member.id)
        .one()
    )


def _new_invite_token(db: DbSession) -> str:
    for _ in range(5):
        token = token_urlsafe(24)
        exists = db.query(ProjectInviteLink.id).filter(ProjectInviteLink.token == token).first()
        if not exists:
            return token
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="邀请链接生成失败")


def _is_expired(invite: ProjectInviteLink) -> bool:
    expires_at = invite.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)
