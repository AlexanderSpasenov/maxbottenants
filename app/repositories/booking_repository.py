from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.booking import Booking


class BookingRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, booking: Booking) -> Booking:
        self.db.add(booking)
        self.db.flush()
        return booking

    def get(self, tenant_id: uuid.UUID, booking_id: uuid.UUID) -> Booking | None:
        stmt = select(Booking).where(Booking.tenant_id == tenant_id, Booking.id == booking_id)
        return self.db.scalar(stmt)

    def get_by_id(self, booking_id: uuid.UUID) -> Booking | None:
        return self.db.get(Booking, booking_id)

    def update_status(self, booking: Booking, status: str) -> Booking:
        booking.status = status
        self.db.add(booking)
        self.db.flush()
        return booking

    def transition_status(
        self,
        *,
        tenant_id: uuid.UUID,
        booking_id: uuid.UUID,
        from_status: str,
        to_status: str,
    ) -> Booking | None:
        stmt = (
            select(Booking)
            .where(
                Booking.id == booking_id,
                Booking.tenant_id == tenant_id,
                Booking.status == from_status,
            )
            .with_for_update()
        )
        booking = self.db.scalar(stmt)
        if booking is None:
            return None
        booking.status = to_status
        self.db.add(booking)
        self.db.flush()
        return booking

    def list_for_user(self, tenant_id: uuid.UUID, max_user_id: int) -> list[Booking]:
        stmt = (
            select(Booking)
            .where(Booking.tenant_id == tenant_id, Booking.max_user_id == max_user_id)
            .order_by(Booking.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def list_for_tenant_day(self, tenant_id: uuid.UUID, day, tz) -> list[Booking]:
        from datetime import datetime, time, timedelta
        start_local = datetime.combine(day, time.min, tzinfo=tz)
        end_local = start_local + timedelta(days=1)
        stmt = (
            select(Booking)
            .where(
                Booking.tenant_id == tenant_id,
                (
                    (Booking.slot_start >= start_local) & (Booking.slot_start < end_local)
                ) | (
                    Booking.slot_start.is_(None)
                    & (Booking.preferred_date == day.isoformat())
                ),
            )
            .order_by(Booking.slot_start.asc().nulls_last(), Booking.created_at.asc())
        )
        return list(self.db.scalars(stmt).all())

    def list_master_bookings_for_day(
        self, tenant_id: uuid.UUID, master_id: uuid.UUID, day, tz
    ) -> list[Booking]:
        from datetime import datetime, time, timedelta

        start_local = datetime.combine(day, time.min, tzinfo=tz)
        end_local = start_local + timedelta(days=1)
        stmt = select(Booking).where(
            Booking.tenant_id == tenant_id,
            Booking.master_id == master_id,
            Booking.status.in_(["awaiting_salon", "confirmed", "pending_confirmation"]),
            Booking.slot_start.is_not(None),
            Booking.slot_start >= start_local,
            Booking.slot_start < end_local,
        )
        return list(self.db.scalars(stmt).all())

    def lock_master(self, tenant_id: uuid.UUID, master_id: uuid.UUID) -> None:
        # Serialize slot assignment per tenant+master within a transaction.
        self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
            {"k": f"{tenant_id}:{master_id}"},
        )

    def has_conflicting_booking(
        self,
        *,
        tenant_id: uuid.UUID,
        master_id: uuid.UUID,
        slot_start,
        slot_end,
        exclude_booking_id: uuid.UUID | None = None,
    ) -> bool:
        stmt = select(Booking.id).where(
            Booking.tenant_id == tenant_id,
            Booking.master_id == master_id,
            Booking.status.in_(["awaiting_salon", "confirmed", "pending_confirmation"]),
            Booking.slot_start.is_not(None),
            Booking.slot_end.is_not(None),
            Booking.slot_start < slot_end,
            Booking.slot_end > slot_start,
        )
        if exclude_booking_id is not None:
            stmt = stmt.where(Booking.id != exclude_booking_id)
        return self.db.scalar(stmt) is not None

    def expire_pending(self, now) -> list[Booking]:
        stmt = (
            select(Booking)
            .where(
                Booking.status == "pending_confirmation",
                Booking.expires_at.is_not(None),
                Booking.expires_at <= now,
            )
            .with_for_update(skip_locked=True)
        )
        rows = list(self.db.scalars(stmt).all())
        for b in rows:
            b.status = "expired"
            self.db.add(b)
        if rows:
            self.db.flush()
        return rows
