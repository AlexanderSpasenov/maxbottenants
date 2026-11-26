from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.webhook import WebhookEvent
from app.repositories.webhook_event_repository import WebhookEventRepository

logger = logging.getLogger(__name__)


class WebhookEventProcessor:
    """Increment 3: minimal dispatch skeleton.

    It marks events as processed and logs them. Business routing (request_only flow)
    is implemented in next increments.
    """

    def __init__(self, db: Session):
        self.db = db
        self.repo = WebhookEventRepository(db)

    def process(self, event: WebhookEvent) -> None:
        self.repo.mark_processing(event)
        try:
            logger.info(
                "Processed webhook event id=%s key=%s type=%s",
                event.id,
                event.event_key,
                event.event_type,
            )
            # TODO Increment 4+: route by event_type/payload into dialog/booking services.
            self.repo.mark_processed(event)
        except Exception as exc:
            logger.exception("Webhook event processing failed: %s", event.event_key)
            self.repo.mark_failed(event, str(exc))
            raise
