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

    from app.repositories.outbox_repository import OutboxRepository
    from app.repositories.tenant_member_repository import TenantMemberRepository

    owns_session = db is None
    db = db or SessionLocal()
    try:
        repo = BookingRepository(db)
        outbox = OutboxRepository(db)
        members = TenantMemberRepository(db)
        expired = repo.expire_pending(datetime.now(UTC))
        for b in expired:
            when = ""
            if b.preferred_date:
                when = f" на {b.preferred_date} {b.preferred_time_range or ''}".strip()
            client_text = f"Бронь #{b.id}{when} истекла. Выберите другое время: /start"
            outbox.enqueue(
                tenant_id=b.tenant_id,
                chat_id=b.chat_id,
                payload={"text": client_text},
                dedupe_key=f"booking:{b.id}:expired_notify:client",
            )
            owner_text = (
                f"Бронь #{b.id}{when} истекла (клиент не подтвердил/время ожидания вышло)."
            )
            for owner in members.list_active_owners(b.tenant_id):
                outbox.enqueue(
                    tenant_id=b.tenant_id,
                    chat_id=owner.max_user_id,
                    payload={"text": owner_text},
                    dedupe_key=f"booking:{b.id}:expired_notify:owner:{owner.max_user_id}",
                )
        if expired:
            logger.info("Expired pending bookings: %s", len(expired))
        db.commit()
        return len(expired)
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
                payload = msg.payload or {}
                text = str(payload.get("text") or "")
                if not text:
                    repo.mark_failed(msg, "empty payload.text", max_attempts=max_attempts)
                    continue
                send_kwargs = {}
                for k in ("user_id", "chat_id", "attachments", "format", "notify", "disable_link_preview"):
                    if k in payload and payload[k] is not None:
                        send_kwargs[k] = payload[k]
                asyncio.run(send_text(msg.chat_id, text, **send_kwargs))
                repo.mark_sent(msg)
                sent += 1
            except Exception as exc:
                logger.exception("Outbox send failed id=%s", msg.id)
                repo.mark_failed(msg, str(exc), max_attempts=max_attempts)
        return sent
    finally:
        db.close()


def run_retention_cleanup() -> dict[str, int | bool]:
    from app.services.admin.retention import RetentionService

    db = SessionLocal()
    try:
        result = RetentionService(db).cleanup(dry_run=False)
        logger.info(
            "Retention cleanup: sent_outbox=%s processed_webhooks=%s sync_logs=%s",
            result.get("sent_outbox_deleted"),
            result.get("processed_webhooks_deleted"),
            result.get("sync_logs_deleted"),
        )
        return result
    finally:
        db.close()


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info(
        "Event worker started; polling interval=%s",
        settings.worker_poll_interval_seconds,
    )
    next_cleanup_at = 0.0
    while True:
        try:
            now_mono = time.monotonic()
            if settings.cleanup_interval_seconds >= 0 and now_mono >= next_cleanup_at:
                try:
                    run_retention_cleanup()
                except Exception:
                    logger.exception("Retention cleanup iteration failed")
                next_cleanup_at = now_mono + max(60, settings.cleanup_interval_seconds)
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
