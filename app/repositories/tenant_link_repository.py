from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tenant_link import TenantLink


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TenantLinkRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_token(self, token: str) -> TenantLink | None:
        token_hash = hash_token(token)
        stmt = select(TenantLink).where(TenantLink.token_hash == token_hash)
        return self.db.scalar(stmt)
