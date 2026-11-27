from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.repositories.booking_repository import BookingRepository
from app.repositories.schedule_repository import ScheduleRepository


@dataclass(frozen=True)
class Slot:
    start: datetime
    end: datetime


def _parse_hhmm(value: str) -> time | None:
    try:
        return datetime.strptime(value.strip(), "%H:%M").time()
    except ValueError:
        return None


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def get_available_slots(
    *,
    db: Session,
    tenant_id,
    master_id,
    service_duration_minutes: int,
    buffer_minutes: int,
    tenant_tz: str,
    days_ahead: int = 7,
    limit: int = 10,
    now: datetime | None = None,
) -> list[Slot]:
    """Minimal slot engine for online_booking.

    - Uses MasterWorkingHours/ScheduleExceptions when present.
    - If no working hours configured, falls back to 10:00-18:00 local.
    - Blocks overlaps with existing non-cancelled bookings for the master.
    """
    now = now or datetime.now(UTC)
    tz = ZoneInfo(tenant_tz or "UTC")
    local_now = now.astimezone(tz)
    schedule_repo = ScheduleRepository(db)
    booking_repo = BookingRepository(db)
    step = timedelta(minutes=max(service_duration_minutes + buffer_minutes, 15))
    duration = timedelta(minutes=service_duration_minutes)

    slots: list[Slot] = []
    for day_offset in range(days_ahead):
        day = (local_now.date() + timedelta(days=day_offset))
        weekday = day.weekday()  # 0=Mon
        wh_rows = schedule_repo.list_working_hours(tenant_id, master_id, weekday)
        windows: list[tuple[time, time]] = []
        if wh_rows:
            windows = [(r.start_time, r.end_time) for r in wh_rows]
        else:
            windows = [(time(10, 0), time(18, 0))]

        exceptions = schedule_repo.list_exceptions(tenant_id, master_id, day)
        day_off = any(e.type == "day_off" for e in exceptions)
        if day_off:
            continue
        blocked = [
            (e.start_time, e.end_time)
            for e in exceptions
            if e.type in {"blocked", "break", "exception"}
        ]

        # Existing bookings for master on this day (tenant-scoped)
        existing = booking_repo.list_master_bookings_for_day(tenant_id, master_id, day, tz)

        for start_t, end_t in windows:
            cursor = datetime.combine(day, start_t, tzinfo=tz)
            window_end = datetime.combine(day, end_t, tzinfo=tz)
            while cursor + duration <= window_end:
                slot_start = cursor
                slot_end = cursor + duration
                cursor += step

                if slot_start <= local_now + timedelta(minutes=15):
                    continue

                # blocked exceptions
                blocked_hit = False
                for b_start_t, b_end_t in blocked:
                    b_start = datetime.combine(day, b_start_t, tzinfo=tz)
                    b_end = datetime.combine(day, b_end_t, tzinfo=tz)
                    if _overlaps(slot_start, slot_end, b_start, b_end):
                        blocked_hit = True
                        break
                if blocked_hit:
                    continue

                conflict = False
                for b in existing:
                    if b.slot_start and b.slot_end and _overlaps(
                        slot_start, slot_end, b.slot_start.astimezone(tz), b.slot_end.astimezone(tz)
                    ):
                        conflict = True
                        break
                    # request_only without slot_start: no hard block
                if conflict:
                    continue

                slots.append(
                    Slot(start=slot_start.astimezone(UTC), end=slot_end.astimezone(UTC))
                )
                if len(slots) >= limit:
                    return slots
    return slots
