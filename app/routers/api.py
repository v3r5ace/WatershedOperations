from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, hash_password, require_roles
from app.config import get_settings
from app.database import get_db
from app.models import CalendarEvent, MaintenanceTask, TaskStatus, User, UserRole
from app.schemas import TaskCreate, TaskUpdate, UserCreate
from app.services.calendar import sync_calendar_from_url


router = APIRouter(prefix="/api")


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role.value,
    }


@router.get("/tasks")
def list_tasks(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(MaintenanceTask).order_by(MaintenanceTask.created_at.desc())
    if user.role == UserRole.staff:
        query = query.filter(MaintenanceTask.assignee_id == user.id)
    tasks = query.all()
    return [
        {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "area": task.area,
            "priority": task.priority.value,
            "status": task.status.value,
            "due_at": task.due_at.isoformat() if task.due_at else None,
            "assignee": task.assignee.full_name if task.assignee else None,
        }
        for task in tasks
    ]


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    task = MaintenanceTask(**payload.model_dump(), created_by_id=user.id)
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"id": task.id}


@router.patch("/tasks/{task_id}")
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = db.query(MaintenanceTask).filter(MaintenanceTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    is_manager = user.role in {UserRole.admin, UserRole.manager}
    is_assignee = task.assignee_id == user.id
    if not is_manager and not is_assignee:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    updates = payload.model_dump(exclude_unset=True)
    if not is_manager:
        disallowed = {"title", "description", "area", "priority", "assignee_id"}
        if disallowed.intersection(updates):
            raise HTTPException(status_code=403, detail="Only managers can edit task details")
        if updates.get("status") not in {None, TaskStatus.in_progress, TaskStatus.completed, TaskStatus.pending}:
            raise HTTPException(status_code=400, detail="Invalid task status")

    for field, value in updates.items():
        setattr(task, field, value)

    db.commit()
    return {"success": True}


@router.get("/events")
def list_events(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    events = db.query(CalendarEvent).order_by(CalendarEvent.start_at.asc()).all()
    return [
        {
            "id": event.id,
            "title": event.title,
            "location": event.location,
            "start_at": event.start_at.isoformat(),
            "end_at": event.end_at.isoformat(),
            "description": event.description,
        }
        for event in events
    ]


@router.post("/events/sync")
async def sync_events(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    source_url = get_settings().calendar_ics_url
    if not source_url:
        raise HTTPException(status_code=400, detail="CALENDAR_ICS_URL is not configured")
    imported = await sync_calendar_from_url(db, source_url)
    return {"imported": imported}


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="A user with that email already exists")

    user = User(
        full_name=payload.full_name,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id}
