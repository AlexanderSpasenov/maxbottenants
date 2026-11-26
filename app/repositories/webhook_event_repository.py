from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.webhook import WebhookEvent


class WebhookEventRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_event_key(self, event_key: str) -> WebhookEvent | None:
        stmt = select(WebhookEvent).where(WebhookEvent.event_key == event_key)
        return self.db.scalar(stmt)

    def create_received(
        self, *, event_key: str, event_type: str, payload: dict
    ) -> tuple[WebhookEvent, bool]:
        existing = self.get_by_event_key(event_key)
        if existing is not None:
            return existing, False

        event = WebhookEvent(
            id=uuid.uuid4(),
            event_key=event_key,
            event_type=event_type,
            payload=payload,
            status="received",
            attempts=0,
        )
        self.db.add(event)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            existing = self.get_by_event_key(event_key)
            if existing is None:
                raise
            return existing, False
        return event, True

    def list_pending(self, limit: int = 100) -> list[WebhookEvent]:
        stmt = (
            select(WebhookEvent)
            .where(WebhookEvent.status.in_(["received", "failed"]))
            .order_by(WebhookEvent.received_at.asc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def mark_processing(self, event: WebhookEvent) -> None:
        event.status = "processing"
        event.attempts = (event.attempts or 0) + 1
        event.last_error = None
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)

    def mark_processed(self, event: WebhookEvent) -> None:
        event.status = "processed"
        event.processed_at = datetime.now(UTC)
        event.last_error = None
        self.db.add(event)
        self.db.commit()

    def mark_failed(self, event: WebhookEvent, error: str) -> None:
        event.status = "failed"
        event.last_error = error[:4000]
        self.db.add(event)
        self.db.commit()
