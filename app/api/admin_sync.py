from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.integrations.sheets.csv_source import CsvCatalogSource
from app.models.sync_log import SyncLog
from app.models.tenant import Tenant
from app.repositories.outbox_repository import OutboxRepository
from app.services.sync.catalog_sync import CatalogSyncService

router = APIRouter(tags=["admin-sync"])


def require_admin_sync_secret(x_admin_sync_secret: str | None = Header(default=None)) -> None:
    settings = get_settings()
    expected = settings.admin_sync_secret
    if not expected:
        return  # dev mode allowed, warned by config validation
    if not x_admin_sync_secret or x_admin_sync_secret != expected:
        raise HTTPException(status_code=401, detail="Invalid admin sync secret")


@router.post("/admin/sync/{tenant_slug}/csv")
async def sync_tenant_csv(
    tenant_slug: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_sync_secret),
) -> dict[str, Any]:
    base_dir = str(payload.get("base_dir") or "").strip()
    if not base_dir and not isinstance(payload.get("catalog"), dict):
        raise HTTPException(status_code=400, detail="base_dir or catalog is required")

    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    mode = str(payload.get("mode") or "upsert_only").strip().lower()
    if isinstance(payload.get("catalog"), dict):
        catalog = payload["catalog"]
    else:
        source = CsvCatalogSource(base_dir)
        catalog = await source.fetch_tenant_catalog(str(tenant.id))

    try:
        log = CatalogSyncService(db).sync_tenant_catalog(tenant.id, catalog, mode=mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": log.status == "ok",
        "tenant_slug": tenant_slug,
        "status": log.status,
        "mode": mode,
        "services_upserted": log.services_upserted,
        "masters_upserted": log.masters_upserted,
        "schedule_rows_upserted": log.schedule_rows_upserted,
        "deactivated": log.deactivated,
        "error": log.error_message,
    }


@router.get("/admin/sync/{tenant_slug}/logs")
def get_sync_logs(
    tenant_slug: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_sync_secret),
) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    rows = list(
        db.scalars(
            select(SyncLog)
            .where(SyncLog.tenant_id == tenant.id)
            .order_by(SyncLog.started_at.desc())
            .limit(limit)
        ).all()
    )
    return {
        "tenant_slug": tenant_slug,
        "logs": [
            {
                "id": r.id,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "services_upserted": r.services_upserted,
                "masters_upserted": r.masters_upserted,
                "schedule_rows_upserted": r.schedule_rows_upserted,
                "deactivated": r.deactivated,
                "error": r.error_message,
            }
            for r in rows
        ],
    }


@router.get("/admin/outbox")
def get_outbox_messages(
    status: str = Query(default="dead"),
    tenant_slug: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_sync_secret),
) -> dict[str, Any]:
    if status not in {"pending", "failed", "sending", "sent", "dead"}:
        raise HTTPException(status_code=400, detail="Invalid status")
    tenant_id = None
    if tenant_slug:
        tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        tenant_id = tenant.id
    repo = OutboxRepository(db)
    rows = repo.list_by_status(status=status, tenant_id=tenant_id, limit=limit)
    return {
        "status": status,
        "tenant_slug": tenant_slug,
        "messages": [
            {
                "id": str(m.id),
                "tenant_id": str(m.tenant_id) if m.tenant_id else None,
                "chat_id": m.chat_id,
                "status": m.status,
                "attempts": m.attempts,
                "last_error": m.last_error,
                "next_attempt_at": m.next_attempt_at.isoformat() if m.next_attempt_at else None,
                "scheduled_at": m.scheduled_at.isoformat() if m.scheduled_at else None,
                "sent_at": m.sent_at.isoformat() if m.sent_at else None,
                "dedupe_key": m.dedupe_key,
            }
            for m in rows
        ],
    }


@router.post("/admin/outbox/requeue")
def requeue_outbox_dead(
    payload: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_sync_secret),
) -> dict[str, Any]:
    payload = payload or {}
    tenant_slug = payload.get("tenant_slug")
    limit = int(payload.get("limit") or 100)
    limit = max(1, min(limit, 500))
    tenant_id = None
    if tenant_slug:
        tenant = db.query(Tenant).filter(Tenant.slug == str(tenant_slug)).first()
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        tenant_id = tenant.id
    count = OutboxRepository(db).requeue_dead(tenant_id=tenant_id, limit=limit)
    return {"ok": True, "tenant_slug": tenant_slug, "requeued": count}


@router.get("/admin/stats")
def get_admin_stats(
    tenant_slug: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin_sync_secret),
) -> dict[str, Any]:
    from app.repositories.webhook_event_repository import WebhookEventRepository

    tenant_id = None
    if tenant_slug:
        tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        tenant_id = tenant.id
    outbox = OutboxRepository(db).stats(tenant_id=tenant_id)
    webhooks = WebhookEventRepository(db).stats()
    return {"tenant_slug": tenant_slug, "outbox": outbox, "webhooks": webhooks}
