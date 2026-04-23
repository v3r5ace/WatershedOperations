from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, hash_password, require_roles
from app.config import get_settings
from app.database import get_db
from app.models import CalendarEvent, LayoutType, MaintenanceTask, TaskStatus, User, UserRole, VenueRoom
from app.schemas import LayoutTypeCreate, TaskCreate, TaskUpdate, UserCreate, VenueRoomCreate, VenueRoomLayoutUpdate
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


@router.delete("/tasks/{task_id}")
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    task = db.query(MaintenanceTask).filter(MaintenanceTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
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


@router.post("/layout-types", status_code=status.HTTP_201_CREATED)
def create_layout_type(
    payload: LayoutTypeCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    existing = db.query(LayoutType).filter(LayoutType.name == payload.name.strip()).first()
    if existing:
        raise HTTPException(status_code=409, detail="A layout type with that name already exists")

    layout_type = LayoutType(name=payload.name.strip(), description=payload.description.strip(), is_active=True)
    db.add(layout_type)
    db.commit()
    db.refresh(layout_type)
    return {"id": layout_type.id}


@router.delete("/layout-types/{layout_type_id}")
def delete_layout_type(
    layout_type_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    layout_type = db.query(LayoutType).filter(LayoutType.id == layout_type_id).first()
    if not layout_type:
        raise HTTPException(status_code=404, detail="Layout type not found")

    rooms = db.query(VenueRoom).filter(VenueRoom.current_layout_type_id == layout_type.id).all()
    for room in rooms:
        room.current_layout_type_id = None

    db.delete(layout_type)
    db.commit()
    return {"success": True}


@router.post("/rooms", status_code=status.HTTP_201_CREATED)
def create_room(
    payload: VenueRoomCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    existing = db.query(VenueRoom).filter(VenueRoom.name == payload.name.strip()).first()
    if existing:
        raise HTTPException(status_code=409, detail="A room with that name already exists")

    room = VenueRoom(name=payload.name.strip(), notes=payload.notes.strip(), is_active=True)
    db.add(room)
    db.commit()
    db.refresh(room)
    return {"id": room.id}


@router.delete("/rooms/{room_id}")
def delete_room(
    room_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    room = db.query(VenueRoom).filter(VenueRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    db.delete(room)
    db.commit()
    return {"success": True}


@router.patch("/rooms/{room_id}/layout")
def update_room_layout(
    room_id: int,
    payload: VenueRoomLayoutUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin, UserRole.manager)),
):
    room = db.query(VenueRoom).filter(VenueRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if payload.current_layout_type_id is not None:
        layout_type = db.query(LayoutType).filter(LayoutType.id == payload.current_layout_type_id).first()
        if not layout_type:
            raise HTTPException(status_code=404, detail="Layout type not found")

    room.current_layout_type_id = payload.current_layout_type_id
    db.commit()
    return {"success": True}
