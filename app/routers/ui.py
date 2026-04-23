from __future__ import annotations

import calendar
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import authenticate_user, can_manage_tasks
from app.config import get_settings
from app.database import get_db
from app.models import CalendarEvent, MaintenanceTask, TaskPriority, TaskStatus, User, UserRole
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
        .all()
    )
    recent_tasks = tasks[:6]
    events = db.query(CalendarEvent).order_by(CalendarEvent.start_at.asc()).all()
    users = db.query(User).order_by(User.full_name.asc()).all()
    now = datetime.utcnow()
    month_weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(now.year, now.month)

    events_by_day = {}
    for event in events:
        day_key = event.start_at.date().isoformat()
        events_by_day.setdefault(day_key, []).append(
            {
                "id": event.id,
                "title": event.title,
                "location": event.location,
                "description": event.description,
                "start_at": event.start_at.strftime("%a, %b %d at %I:%M %p"),
                "end_at": event.end_at.strftime("%I:%M %p"),
            }
        )

    calendar_days = []
    for week in month_weeks:
        week_days = []
        for day in week:
            day_key = day.isoformat()
            week_days.append(
                {
                    "date": day,
                    "day_number": day.day,
                    "iso": day_key,
                    "in_month": day.month == now.month,
                    "event_count": len(events_by_day.get(day_key, [])),
                }
            )
        calendar_days.append(week_days)

    task_payload = [
        {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "area": task.area,
            "priority": task.priority.value,
            "status": task.status.value,
            "due_at": task.due_at.strftime("%b %d, %Y %I:%M %p") if task.due_at else "No deadline",
            "due_at_value": task.due_at.strftime("%Y-%m-%dT%H:%M") if task.due_at else "",
            "assignee_id": task.assignee_id,
            "assignee_name": task.assignee.full_name if task.assignee else "Unassigned",
        }
        for task in tasks
    ]

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
            "tasks": recent_tasks,
            "events": events[:8],
            "users": users,
            "stats": stats,
            "can_manage_tasks": can_manage_tasks(user.role),
            "can_manage_users": user.role.value == "admin",
            "task_statuses": [status.value for status in TaskStatus],
            "task_priorities": [priority.value for priority in TaskPriority],
            "user_roles": [role.value for role in UserRole],
            "now": now,
            "month_label": now.strftime("%B %Y"),
            "calendar_days": calendar_days,
            "events_json": json.dumps(events_by_day),
            "tasks_json": json.dumps(task_payload),
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
