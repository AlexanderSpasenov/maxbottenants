from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_profile import CustomerProfile


class CustomerProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, tenant_id: uuid.UUID, max_user_id: int) -> CustomerProfile | None:
        stmt = select(CustomerProfile).where(
            CustomerProfile.tenant_id == tenant_id,
            CustomerProfile.max_user_id == max_user_id,
        )
        return self.db.scalar(stmt)

    def upsert(
        self,
        *,
        tenant_id: uuid.UUID,
        max_user_id: int,
        display_name: str | None = None,
        phone_encrypted: str | None = None,
    ) -> CustomerProfile:
        profile = self.get(tenant_id, max_user_id)
        if profile is None:
            profile = CustomerProfile(
                tenant_id=tenant_id,
                max_user_id=max_user_id,
                display_name=display_name,
                phone_encrypted=phone_encrypted,
            )
            self.db.add(profile)
        else:
            if display_name:
                profile.display_name = display_name
            if phone_encrypted is not None:
                profile.phone_encrypted = phone_encrypted
        self.db.flush()
        return profile
