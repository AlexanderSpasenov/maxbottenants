from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.schedule import MasterWorkingHours, ScheduleException


class ScheduleRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_working_hours(
        self, tenant_id: uuid.UUID, master_id: uuid.UUID | None, weekday: int
    ) -> list[MasterWorkingHours]:
        stmt = select(MasterWorkingHours).where(
            MasterWorkingHours.tenant_id == tenant_id,
            MasterWorkingHours.weekday == weekday,
            MasterWorkingHours.is_working.is_(True),
            or_(
                MasterWorkingHours.master_id == master_id,
                MasterWorkingHours.master_id.is_(None),
            ),
        )
        return list(self.db.scalars(stmt).all())

    def list_exceptions(
        self, tenant_id: uuid.UUID, master_id: uuid.UUID | None, day: date
    ) -> list[ScheduleException]:
        stmt = select(ScheduleException).where(
            ScheduleException.tenant_id == tenant_id,
            ScheduleException.date == day,
            or_(
                ScheduleException.master_id == master_id,
                ScheduleException.master_id.is_(None),
            ),
        )
        return list(self.db.scalars(stmt).all())
