import logging
import time

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.repositories.webhook_event_repository import WebhookEventRepository
from app.services.webhooks.processor import WebhookEventProcessor

logger = logging.getLogger(__name__)


def process_pending_events(batch_size: int = 100) -> int:
    db = SessionLocal()
    try:
        repo = WebhookEventRepository(db)
        events = repo.list_pending(limit=batch_size)
        processed = 0
        for event in events:
            processor = WebhookEventProcessor(db)
            try:
                processor.process(event)
                processed += 1
            except Exception:
                # mark_failed already called in processor; continue batch
                continue
        return processed
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
            processed = process_pending_events()
            if processed:
                logger.info("Processed %s webhook events", processed)
        except Exception:
            logger.exception("Worker polling iteration failed")
        time.sleep(settings.worker_poll_interval_seconds)


if __name__ == "__main__":
    run()
