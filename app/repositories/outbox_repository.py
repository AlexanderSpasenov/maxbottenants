from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
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
        dedupe_key: str | None = None,
        next_attempt_at: datetime | None = None,
    ) -> OutboxMessage:
        if dedupe_key:
            stmt = select(OutboxMessage).where(
                OutboxMessage.tenant_id == tenant_id,
                OutboxMessage.dedupe_key == dedupe_key,
            )
            existing = self.db.scalar(stmt)
            if existing is not None:
                return existing

        msg = OutboxMessage(
            tenant_id=tenant_id,
            chat_id=chat_id,
            payload=payload,
            status="pending",
            attempts=0,
            dedupe_key=dedupe_key,
            next_attempt_at=next_attempt_at or datetime.now(UTC),
        )
        self.db.add(msg)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            if dedupe_key:
                existing = self.db.scalar(
                    select(OutboxMessage).where(
                        OutboxMessage.tenant_id == tenant_id,
                        OutboxMessage.dedupe_key == dedupe_key,
                    )
                )
                if existing is not None:
                    return existing
            raise
        return msg

    def claim_pending(self, limit: int = 100, max_attempts: int = 5) -> list[OutboxMessage]:
        now = datetime.now(UTC)
        stmt = (
            select(OutboxMessage)
            .where(
                OutboxMessage.status.in_(["pending", "failed"]),
                OutboxMessage.next_attempt_at <= now,
                OutboxMessage.attempts < max_attempts,
            )
            .order_by(OutboxMessage.next_attempt_at.asc(), OutboxMessage.scheduled_at.asc())
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

    def mark_failed(self, msg: OutboxMessage, error: str, max_attempts: int = 5) -> None:
        msg.last_error = error[:4000]
        if (msg.attempts or 0) >= max_attempts:
            msg.status = "dead"
            msg.next_attempt_at = datetime.now(UTC)
        else:
            msg.status = "failed"
            backoff_seconds = min(300, 2 ** max((msg.attempts or 1) - 1, 0) * 15)
            msg.next_attempt_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds)
        self.db.add(msg)
        self.db.commit()

    def list_by_status(
        self, *, status: str, tenant_id: uuid.UUID | None = None, limit: int = 50
    ) -> list[OutboxMessage]:
        stmt = select(OutboxMessage).where(OutboxMessage.status == status)
        if tenant_id is not None:
            stmt = stmt.where(OutboxMessage.tenant_id == tenant_id)
        stmt = stmt.order_by(OutboxMessage.scheduled_at.desc()).limit(limit)
        return list(self.db.scalars(stmt).all())
