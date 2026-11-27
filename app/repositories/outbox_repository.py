from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.outbox import OutboxMessage


class OutboxRepository:
    def __init__(self, db: Session):
        self.db = db

    def enqueue(
        self,
        *,
        tenant_id: uuid.UUID | None,
        chat_id: int,
        payload: dict,
    ) -> OutboxMessage:
        msg = OutboxMessage(
            tenant_id=tenant_id,
            chat_id=chat_id,
            payload=payload,
            status="pending",
            attempts=0,
        )
        self.db.add(msg)
        self.db.flush()
        return msg

    def claim_pending(self, limit: int = 100) -> list[OutboxMessage]:
        stmt = (
            select(OutboxMessage)
            .where(OutboxMessage.status.in_(["pending", "failed"]))
            .order_by(OutboxMessage.scheduled_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        msgs = list(self.db.scalars(stmt).all())
        for msg in msgs:
            msg.status = "sending"
            msg.attempts = (msg.attempts or 0) + 1
            msg.last_error = None
            self.db.add(msg)
        if msgs:
            self.db.commit()
            for msg in msgs:
                self.db.refresh(msg)
        return msgs

    def mark_sent(self, msg: OutboxMessage) -> None:
        msg.status = "sent"
        msg.sent_at = datetime.now(UTC)
        msg.last_error = None
        self.db.add(msg)
        self.db.commit()

    def mark_failed(self, msg: OutboxMessage, error: str) -> None:
        msg.status = "failed"
        msg.last_error = error[:4000]
        self.db.add(msg)
        self.db.commit()
