from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.models import TaskPriority, TaskStatus, UserRole


class LoginForm(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = ""
    area: str = Field(default="General", max_length=120)
    priority: TaskPriority = TaskPriority.medium
    status: TaskStatus = TaskStatus.pending
    due_at: Optional[datetime] = None
    assignee_id: Optional[int] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    description: Optional[str] = None
    area: Optional[str] = Field(default=None, max_length=120)
    priority: Optional[TaskPriority] = None
    status: Optional[TaskStatus] = None
    due_at: Optional[datetime] = None
    assignee_id: Optional[int] = None


class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8)
    role: UserRole
