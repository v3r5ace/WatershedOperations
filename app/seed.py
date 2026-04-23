from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import get_settings
from app.models import LayoutType, MaintenanceTask, TaskPriority, TaskStatus, User, UserRole, VenueRoom


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

    default_layouts = [
        ("Classroom Seating", "Rows facing the front for teaching sessions and seminars."),
        ("Round Tables", "Small-group table setup for receptions, meals, and discussions."),
        ("Reception Open Floor", "Open circulation layout for mingling and standing-room gatherings."),
        ("Funeral Seating", "Reserved seating with center aisle and hospitality support."),
    ]
    for name, description in default_layouts:
        if not db.query(LayoutType).filter(LayoutType.name == name).first():
            db.add(LayoutType(name=name, description=description, is_active=True))

    db.flush()

    default_rooms = [
        ("Children's Lobby", "Overflow gathering and family check-in area."),
        ("Main Lobby", "Welcome and reception area for guests and renters."),
        ("Sanctuary", "Primary worship and ceremony space."),
    ]
    first_layout = db.query(LayoutType).filter(LayoutType.name == "Classroom Seating").first()
    for name, notes in default_rooms:
        room = db.query(VenueRoom).filter(VenueRoom.name == name).first()
        if not room:
            db.add(
                VenueRoom(
                    name=name,
                    notes=notes,
                    is_active=True,
                    current_layout_type_id=first_layout.id if first_layout else None,
                )
            )
    db.commit()
