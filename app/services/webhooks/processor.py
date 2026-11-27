from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.webhook import WebhookEvent
from app.repositories.webhook_event_repository import WebhookEventRepository
from app.services.dialogs.service import DialogService

logger = logging.getLogger(__name__)


class WebhookEventProcessor:
    """Routes webhook events to dialog/booking services."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = WebhookEventRepository(db)
        self.dialogs = DialogService(db)

    def process(self, event: WebhookEvent) -> None:
        try:
            logger.info(
                "Processing webhook event id=%s key=%s type=%s attempts=%s",
                event.id,
                event.event_key,
                event.event_type,
                event.attempts,
            )
            responses = self.dialogs.handle_event(event.payload or {})
            logger.info(
                "Dialog produced %s responses for event=%s",
                len(responses),
                event.event_key,
            )
            self.repo.mark_processed(event)
        except Exception as exc:
            logger.exception("Webhook event processing failed: %s", event.event_key)
            self.repo.mark_failed(event, str(exc))
            raise
