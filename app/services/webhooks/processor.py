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
            if responses:
                from app.repositories.outbox_repository import OutboxRepository
                outbox = OutboxRepository(self.db)
                for resp in responses:
                    chat_id = resp.get("chat_id")
                    text = resp.get("text")
                    if not chat_id or not text:
                        continue
                    payload = {"text": text}
                    for k, v in resp.items():
                        if k not in {"chat_id", "text"}:
                            payload[k] = v
                    dedupe = f"webhook:{event.event_key}:reply:{chat_id}:{hash(text)}"
                    outbox.enqueue(
                        tenant_id=None,
                        chat_id=int(chat_id),
                        payload=payload,
                        dedupe_key=dedupe,
                    )
            # Best-effort: acknowledge callback to remove MAX client loading state.
            try:
                if (event.event_type or "") == "message_callback":
                    from app.services.webhooks.normalizer import normalize_max_event
                    from app.services.max.sender import get_max_client
                    import asyncio
                    cb_id = normalize_max_event(event.payload or {}).get("callback_id")
                    if cb_id:
                        asyncio.run(get_max_client().answer_callback(str(cb_id)))
            except Exception:
                logger.warning("Callback answer failed for event=%s", event.event_key, exc_info=True)
            self.repo.mark_processed(event)
        except Exception as exc:
            logger.exception("Webhook event processing failed: %s", event.event_key)
            self.repo.mark_failed(event, str(exc))
            raise
