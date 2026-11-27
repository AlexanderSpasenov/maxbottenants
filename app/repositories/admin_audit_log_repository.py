from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admin_audit_log import AdminAuditLog


class AdminAuditLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        *,
        action: str,
        status: str,
        tenant_id: uuid.UUID | None = None,
        tenant_slug: str | None = None,
        request_summary: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> AdminAuditLog:
        row = AdminAuditLog(
            action=action,
            status=status,
            tenant_id=tenant_id,
            tenant_slug=tenant_slug,
            request_summary=request_summary,
            error=(error[:4000] if error else None),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list(
        self,
        *,
        tenant_id: uuid.UUID | None = None,
        tenant_slug: str | None = None,
        limit: int = 50,
    ) -> list[AdminAuditLog]:
        stmt = select(AdminAuditLog)
        if tenant_id is not None:
            stmt = stmt.where(AdminAuditLog.tenant_id == tenant_id)
        if tenant_slug:
            stmt = stmt.where(AdminAuditLog.tenant_slug == tenant_slug)
        stmt = stmt.order_by(AdminAuditLog.created_at.desc()).limit(limit)
        return list(self.db.scalars(stmt).all())
