from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.outbox import OutboxMessage
from app.models.sync_log import SyncLog
from app.models.webhook import WebhookEvent


class RetentionService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def cleanup(
        self, *, dry_run: bool = True, now: datetime | None = None
    ) -> dict[str, int | bool]:
        now = now or datetime.now(UTC)
        outbox_cutoff = now - timedelta(days=max(0, self.settings.retention_sent_outbox_days))
        webhook_cutoff = now - timedelta(
            days=max(0, self.settings.retention_processed_webhook_days)
        )
        sync_cutoff = now - timedelta(days=max(0, self.settings.retention_sync_log_days))

        outbox_stmt = select(func.count()).select_from(OutboxMessage).where(
            OutboxMessage.status == "sent",
            OutboxMessage.sent_at.is_not(None),
            OutboxMessage.sent_at < outbox_cutoff,
        )
        webhook_stmt = select(func.count()).select_from(WebhookEvent).where(
            WebhookEvent.status == "processed",
            WebhookEvent.processed_at.is_not(None),
            WebhookEvent.processed_at < webhook_cutoff,
        )
        sync_stmt = select(func.count()).select_from(SyncLog).where(
            SyncLog.created_at < sync_cutoff,
        )

        result = {
            "dry_run": bool(dry_run),
            "sent_outbox_eligible": int(self.db.scalar(outbox_stmt) or 0),
            "processed_webhooks_eligible": int(self.db.scalar(webhook_stmt) or 0),
            "sync_logs_eligible": int(self.db.scalar(sync_stmt) or 0),
            "sent_outbox_deleted": 0,
            "processed_webhooks_deleted": 0,
            "sync_logs_deleted": 0,
        }

        if dry_run:
            return result

        outbox_del = delete(OutboxMessage).where(
            OutboxMessage.status == "sent",
            OutboxMessage.sent_at.is_not(None),
            OutboxMessage.sent_at < outbox_cutoff,
        )
        webhook_del = delete(WebhookEvent).where(
            WebhookEvent.status == "processed",
            WebhookEvent.processed_at.is_not(None),
            WebhookEvent.processed_at < webhook_cutoff,
        )
        sync_del = delete(SyncLog).where(SyncLog.created_at < sync_cutoff)

        result["sent_outbox_deleted"] = int(self.db.execute(outbox_del).rowcount or 0)
        result["processed_webhooks_deleted"] = int(self.db.execute(webhook_del).rowcount or 0)
        result["sync_logs_deleted"] = int(self.db.execute(sync_del).rowcount or 0)
        self.db.commit()
        return result
