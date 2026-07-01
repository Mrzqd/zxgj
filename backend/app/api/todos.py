from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession, require_project_member
from app.models import Todo
from app.schemas import TodoCreate, TodoRead, TodoUpdate
from app.services.activity import log_activity

router = APIRouter(prefix="/projects/{project_id}/todos", tags=["todos"])


@router.get("", response_model=list[TodoRead])
def list_todos(project_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    return (
        db.query(Todo)
        .filter(Todo.project_id == project_id)
        .order_by(Todo.status.asc(), Todo.due_at.asc().nullslast(), Todo.importance.desc())
        .all()
    )


@router.post("", response_model=TodoRead, status_code=status.HTTP_201_CREATED)
def create_todo(project_id: int, payload: TodoCreate, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    todo = Todo(project_id=project_id, **payload.model_dump())
    db.add(todo)
    db.flush()
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="create",
        target_type="todo",
        target_id=todo.id,
        message=f"新增待办：{todo.title}",
    )
    db.commit()
    db.refresh(todo)
    return todo


@router.patch("/{todo_id}", response_model=TodoRead)
def update_todo(project_id: int, todo_id: int, payload: TodoUpdate, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    todo = db.get(Todo, todo_id)
    if not todo or todo.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="待办不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(todo, field, value)
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="update",
        target_type="todo",
        target_id=todo.id,
        message=f"更新待办：{todo.title}",
    )
    db.commit()
    db.refresh(todo)
    return todo


@router.delete("/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(project_id: int, todo_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    todo = db.get(Todo, todo_id)
    if not todo or todo.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="待办不存在")
    log_activity(
        db,
        project_id=project_id,
        actor=user,
        action="delete",
        target_type="todo",
        target_id=todo.id,
        message=f"删除待办：{todo.title}",
    )
    db.delete(todo)
    db.commit()
    return None
