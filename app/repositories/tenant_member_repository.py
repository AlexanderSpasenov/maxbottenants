from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tenant_member import TenantMember


class TenantMemberRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_tenant_user(self, tenant_id: uuid.UUID, max_user_id: int) -> TenantMember | None:
        stmt = select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.max_user_id == max_user_id,
            TenantMember.is_active.is_(True),
        )
        return self.db.scalar(stmt)

    def create(
        self, *, tenant_id: uuid.UUID, max_user_id: int, role: str
    ) -> TenantMember:
        member = TenantMember(
            tenant_id=tenant_id, max_user_id=max_user_id, role=role, is_active=True
        )
        self.db.add(member)
        self.db.flush()
        return member

    def list_active_owners(self, tenant_id: uuid.UUID) -> list[TenantMember]:
        stmt = select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.role == "owner",
            TenantMember.is_active.is_(True),
        )
        return list(self.db.scalars(stmt).all())
