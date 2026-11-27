import asyncio
import logging
import time

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.repositories.booking_repository import BookingRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.webhook_event_repository import WebhookEventRepository
from app.services.max.sender import send_text
from app.services.webhooks.processor import WebhookEventProcessor

logger = logging.getLogger(__name__)


def process_pending_events(
    batch_size: int = 100,
    stale_after_seconds: int = 300,
    db=None,
) -> int:
    owns_session = db is None
    db = db or SessionLocal()
    try:
        repo = WebhookEventRepository(db)
        events = repo.claim_pending(limit=batch_size, stale_after_seconds=stale_after_seconds)
        processed = 0
        for event in events:
            processor = WebhookEventProcessor(db)
            try:
                processor.process(event)
                processed += 1
            except Exception:
                continue
        return processed
    finally:
        if owns_session:
            db.close()


def expire_pending_bookings(db=None) -> int:
    from datetime import UTC, datetime

    owns_session = db is None
    db = db or SessionLocal()
    try:
        repo = BookingRepository(db)
        expired = repo.expire_pending(datetime.now(UTC))
        db.commit()
        return expired
    finally:
        if owns_session:
            db.close()


def process_outbox_messages(batch_size: int = 100, max_attempts: int = 5) -> int:
    db = SessionLocal()
    try:
        repo = OutboxRepository(db)
        messages = repo.claim_pending(limit=batch_size, max_attempts=max_attempts)
        sent = 0
        for msg in messages:
            try:
                text = str((msg.payload or {}).get("text") or "")
                if not text:
                    repo.mark_failed(msg, "empty payload.text", max_attempts=max_attempts)
                    continue
                asyncio.run(send_text(msg.chat_id, text))
                repo.mark_sent(msg)
                sent += 1
            except Exception as exc:
                logger.exception("Outbox send failed id=%s", msg.id)
                repo.mark_failed(msg, str(exc), max_attempts=max_attempts)
        return sent
    finally:
        db.close()


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info(
        "Event worker started; polling interval=%s",
        settings.worker_poll_interval_seconds,
    )
    while True:
        try:
            expired = expire_pending_bookings()
            processed = process_pending_events(
                batch_size=settings.worker_batch_size,
                stale_after_seconds=settings.worker_stale_processing_seconds,
            )
            sent = process_outbox_messages(
                batch_size=settings.worker_batch_size,
                max_attempts=settings.outbox_max_attempts,
            )
            if processed or sent or expired:
                logger.info(
                    "Processed %s webhook events, sent %s outbox, expired %s bookings",
                    processed,
                    sent,
                    expired,
                )
        except Exception:
            logger.exception("Worker polling iteration failed")
        time.sleep(settings.worker_poll_interval_seconds)


if __name__ == "__main__":
    run()
