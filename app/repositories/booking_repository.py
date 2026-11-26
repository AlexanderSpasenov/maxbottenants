import uuid

from sqlalchemy import select
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

    def list_for_user(self, tenant_id: uuid.UUID, max_user_id: int) -> list[Booking]:
        stmt = (
            select(Booking)
            .where(Booking.tenant_id == tenant_id, Booking.max_user_id == max_user_id)
            .order_by(Booking.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())
