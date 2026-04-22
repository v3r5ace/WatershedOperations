from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import get_settings
from app.models import MaintenanceTask, TaskPriority, TaskStatus, User, UserRole


def seed_defaults(db: Session) -> None:
    settings = get_settings()
    admin = db.query(User).filter(User.email == settings.default_admin_email.lower()).first()
    if not admin:
        admin = User(
            full_name="Default Administrator",
            email=settings.default_admin_email.lower(),
            password_hash=hash_password(settings.default_admin_password),
            role=UserRole.admin,
            is_active=True,
        )
        db.add(admin)
        db.flush()

    existing_task = db.query(MaintenanceTask).first()
    if not existing_task:
        db.add_all(
            [
                MaintenanceTask(
                    title="Sanctuary walk-through",
                    description="Check lights, seating, and stage setup for the next service.",
                    area="Sanctuary",
                    priority=TaskPriority.high,
                    status=TaskStatus.pending,
                    due_at=datetime.utcnow() + timedelta(days=2),
                    assignee_id=admin.id,
                    created_by_id=admin.id,
                ),
                MaintenanceTask(
                    title="Lobby refresh",
                    description="Restock welcome materials and inspect signage.",
                    area="Lobby",
                    priority=TaskPriority.medium,
                    status=TaskStatus.in_progress,
                    due_at=datetime.utcnow() + timedelta(days=4),
                    assignee_id=admin.id,
                    created_by_id=admin.id,
                ),
            ]
        )
    db.commit()
