from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import authenticate_user, can_manage_tasks
from app.config import get_settings
from app.database import get_db
from app.models import CalendarEvent, MaintenanceTask, TaskPriority, TaskStatus, User
from app.services.calendar import sync_calendar_from_url


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_dashboard_user(request: Request, db: Session) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "app_name": get_settings().app_name,
            "error": None,
        },
    )


@router.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, email, password)
    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "app_name": get_settings().app_name,
                "error": "Invalid email or password.",
            },
            status_code=401,
        )
    request.session["user_id"] = user.id
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_dashboard_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)

    tasks = (
        db.query(MaintenanceTask)
        .order_by(MaintenanceTask.due_at.is_(None), MaintenanceTask.due_at.asc(), MaintenanceTask.created_at.desc())
        .limit(10)
        .all()
    )
    events = db.query(CalendarEvent).order_by(CalendarEvent.start_at.asc()).limit(10).all()
    users = db.query(User).order_by(User.full_name.asc()).all()

    stats = {
        "open_tasks": db.query(MaintenanceTask).filter(MaintenanceTask.status != TaskStatus.completed).count(),
        "completed_tasks": db.query(MaintenanceTask).filter(MaintenanceTask.status == TaskStatus.completed).count(),
        "events_loaded": db.query(CalendarEvent).count(),
        "team_members": db.query(User).filter(User.is_active.is_(True)).count(),
    }

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "app_name": get_settings().app_name,
            "user": user,
            "tasks": tasks,
            "events": events,
            "users": users,
            "stats": stats,
            "can_manage_tasks": can_manage_tasks(user.role),
            "task_statuses": [status.value for status in TaskStatus],
            "task_priorities": [priority.value for priority in TaskPriority],
            "now": datetime.utcnow(),
            "calendar_url_configured": bool(get_settings().calendar_ics_url),
        },
    )


@router.post("/dashboard/calendar-sync")
async def dashboard_calendar_sync(
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_dashboard_user(request, db)
    if not user:
        return RedirectResponse(url="/", status_code=302)
    if not can_manage_tasks(user.role):
        return RedirectResponse(url="/dashboard", status_code=302)

    source_url = get_settings().calendar_ics_url
    if source_url:
        await sync_calendar_from_url(db, source_url)

    return RedirectResponse(url="/dashboard", status_code=302)
