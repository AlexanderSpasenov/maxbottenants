import uuid
from datetime import date, time

from sqlalchemy import Boolean, Date, ForeignKey, ForeignKeyConstraint, SmallInteger, String, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class MasterWorkingHours(TimestampMixin, Base):
    __tablename__ = "master_working_hours"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "master_id"],
            ["masters.tenant_id", "masters.id"],
            ondelete="CASCADE",
            name="fk_master_working_hours_tenant_master",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    master_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("masters.id", ondelete="CASCADE"), nullable=True, index=True
    )
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_working: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class ScheduleException(TimestampMixin, Base):
    __tablename__ = "schedule_exceptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "master_id"],
            ["masters.tenant_id", "masters.id"],
            ondelete="CASCADE",
            name="fk_schedule_exceptions_tenant_master",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    master_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("masters.id", ondelete="CASCADE"), nullable=True, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(String(255), nullable=True)
