from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

import httpx
from icalendar import Calendar
from sqlalchemy.orm import Session

from app.models import CalendarEvent


def _normalize_datetime(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    return None


async def sync_calendar_from_url(db: Session, source_url: str) -> int:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        response = await client.get(source_url)
        response.raise_for_status()

    calendar = Calendar.from_ical(response.text)
    imported = 0
    now = datetime.utcnow() - timedelta(days=7)

    for component in calendar.walk("VEVENT"):
        start = _normalize_datetime(component.decoded("DTSTART", None))
        end = _normalize_datetime(component.decoded("DTEND", None)) or start
        external_id = str(component.get("UID") or f"{component.get('SUMMARY')}-{start}")
        if not start or start < now:
            continue

        event = db.query(CalendarEvent).filter(CalendarEvent.external_id == external_id).first()
        if not event:
            event = CalendarEvent(external_id=external_id)
            db.add(event)

        event.title = str(component.get("SUMMARY", "Untitled Event"))
        event.description = str(component.get("DESCRIPTION", ""))
        event.location = str(component.get("LOCATION", ""))
        event.start_at = start
        event.end_at = end or start
        event.source_url = source_url
        imported += 1

    db.commit()
    return imported
