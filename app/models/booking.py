import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class Booking(TimestampMixin, Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    max_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    master_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("masters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    slot_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    slot_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    preferred_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    preferred_time_range: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    booking_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    price_snapshot: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    duration_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_phone_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
