from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
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

    def claim_pending(
        self, limit: int = 100, stale_after_seconds: int = 300
    ) -> list[WebhookEvent]:
        now = datetime.now(UTC)
        stale_before = now - timedelta(seconds=stale_after_seconds)
        stmt = (
            select(WebhookEvent)
            .where(
                or_(
                    WebhookEvent.status.in_(["received", "failed"]),
                    (WebhookEvent.status == "processing")
                    & (WebhookEvent.processing_started_at.is_not(None))
                    & (WebhookEvent.processing_started_at < stale_before),
                )
            )
            .order_by(WebhookEvent.received_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        events = list(self.db.scalars(stmt).all())
        for event in events:
            event.status = "processing"
            event.attempts = (event.attempts or 0) + 1
            event.processing_started_at = now
            event.last_error = None
            self.db.add(event)
        if events:
            self.db.commit()
            for event in events:
                self.db.refresh(event)
        return events

    def list_pending(self, limit: int = 100) -> list[WebhookEvent]:
        # Backward-compatible name; now atomically claims events for processing.
        return self.claim_pending(limit=limit)

    def mark_processed(self, event: WebhookEvent) -> None:
        event.status = "processed"
        event.processed_at = datetime.now(UTC)
        event.processing_started_at = None
        event.last_error = None
        self.db.add(event)
        self.db.commit()

    def mark_failed(self, event: WebhookEvent, error: str) -> None:
        event.status = "failed"
        event.processing_started_at = None
        event.last_error = error[:4000]
        self.db.add(event)
        self.db.commit()
