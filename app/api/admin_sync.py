from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.integrations.sheets.csv_source import CsvCatalogSource
from app.models.outbox import OutboxMessage
from app.models.sync_log import SyncLog
from app.models.tenant import Tenant
from app.repositories.admin_audit_log_repository import AdminAuditLogRepository
from app.repositories.outbox_repository import OutboxRepository
from app.services.admin.rbac import AdminPrincipal, resolve_admin_principal
from app.services.admin.retention import RetentionService
from app.services.sync.catalog_sync import CatalogSyncService


def _audit_actor(principal: AdminPrincipal | None) -> dict[str, Any] | None:
    if principal is None:
        return None
    return {
        "subject": principal.subject,
        "role": principal.role,
        "auth_mode": principal.auth_mode,
    }

router = APIRouter(tags=["admin"])


def require_admin_action(action: str):
    def _dep(
        request: Request,
        x_admin_sync_secret: str | None = Header(default=None),
        x_admin_role: str | None = Header(default=None),
    ) -> AdminPrincipal:
        return resolve_admin_principal(
            settings=get_settings(),
            request=request,
            x_admin_sync_secret=x_admin_sync_secret,
            x_admin_role=x_admin_role,
            action=action,
        )

    return _dep


def require_admin_sync_secret(
    request: Request,
    x_admin_sync_secret: str | None = Header(default=None),
    x_admin_role: str | None = Header(default=None),
) -> AdminPrincipal:
    # Backward-compatible default: treat as platform-level admin action.
    return resolve_admin_principal(
        settings=get_settings(),
        request=request,
        x_admin_sync_secret=x_admin_sync_secret,
        x_admin_role=x_admin_role,
        action="*",
    )


def _safe_sync_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "mode": str(payload.get("mode") or "upsert_only"),
        "has_base_dir": bool(str(payload.get("base_dir") or "").strip()),
        "has_catalog": isinstance(payload.get("catalog"), dict),
    }
    catalog = payload.get("catalog")
    if isinstance(catalog, dict):
        for key in [
            "services",
            "masters",
            "service_masters",
            "master_working_hours",
            "schedule_exceptions",
        ]:
            val = catalog.get(key)
            if isinstance(val, list):
                summary[f"{key}_count"] = len(val)
    return summary


@router.post("/admin/sync/{tenant_slug}/csv")
async def sync_tenant_csv(
    tenant_slug: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    _principal: AdminPrincipal = Depends(require_admin_action("admin.sync.run")),
) -> dict[str, Any]:
    audit = AdminAuditLogRepository(db)
    base_dir = str(payload.get("base_dir") or "").strip()
    if not base_dir and not isinstance(payload.get("catalog"), dict):
        audit.log(
            action="sync.csv",
            status="failed",
            tenant_slug=tenant_slug,
            request_summary=_safe_sync_summary(payload),
            error="base_dir or catalog is required",
            actor=_audit_actor(_principal),
        )
        db.commit()
        raise HTTPException(status_code=400, detail="base_dir or catalog is required")

    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None:
        audit.log(
            action="sync.csv",
            status="failed",
            tenant_slug=tenant_slug,
            request_summary=_safe_sync_summary(payload),
            error="Tenant not found",
            actor=_audit_actor(_principal),
        )
        db.commit()
        raise HTTPException(status_code=404, detail="Tenant not found")

    mode = str(payload.get("mode") or "upsert_only").strip().lower()
    summary = _safe_sync_summary(payload)
    if isinstance(payload.get("catalog"), dict):
        catalog = payload["catalog"]
    else:
        source = CsvCatalogSource(base_dir)
        catalog = await source.fetch_tenant_catalog(str(tenant.id))

    try:
        log = CatalogSyncService(db).sync_tenant_catalog(tenant.id, catalog, mode=mode)
        audit.log(
            action="sync.csv",
            status="ok" if log.status == "ok" else "failed",
            tenant_id=tenant.id,
            tenant_slug=tenant_slug,
            request_summary=summary,
            error=log.error_message,
            actor=_audit_actor(_principal),
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        audit.log(
            action="sync.csv",
            status="failed",
            tenant_id=tenant.id,
            tenant_slug=tenant_slug,
            request_summary=summary,
            error=str(exc),
            actor=_audit_actor(_principal),
        )
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        audit.log(
            action="sync.csv",
            status="failed",
            tenant_id=tenant.id,
            tenant_slug=tenant_slug,
            request_summary=summary,
            error=str(exc),
            actor=_audit_actor(_principal),
        )
        db.commit()
        raise

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
    _principal: AdminPrincipal = Depends(require_admin_action("admin.sync.logs.read")),
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
    _principal: AdminPrincipal = Depends(require_admin_action("admin.outbox.read")),
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
    _principal: AdminPrincipal = Depends(require_admin_action("admin.outbox.requeue")),
) -> dict[str, Any]:
    payload = payload or {}
    tenant_slug = payload.get("tenant_slug")
    limit = int(payload.get("limit") or 100)
    limit = max(1, min(limit, 500))
    reset_attempts = bool(payload.get("reset_attempts") or False)
    audit = AdminAuditLogRepository(db)
    tenant_id = None
    resolved_slug = str(tenant_slug) if tenant_slug else None
    if tenant_slug:
        tenant = db.query(Tenant).filter(Tenant.slug == str(tenant_slug)).first()
        if tenant is None:
            audit.log(
                action="outbox.requeue",
                status="failed",
                tenant_slug=resolved_slug,
                request_summary={"limit": limit, "reset_attempts": reset_attempts},
                error="Tenant not found",
                actor=_audit_actor(_principal),
            )
            db.commit()
            raise HTTPException(status_code=404, detail="Tenant not found")
        tenant_id = tenant.id
        resolved_slug = tenant.slug
    try:
        count = OutboxRepository(db).requeue_dead(
            tenant_id=tenant_id, limit=limit, reset_attempts=reset_attempts
        )
        audit.log(
            action="outbox.requeue",
            status="ok",
            tenant_id=tenant_id,
            tenant_slug=resolved_slug,
            request_summary={
                "limit": limit,
                "reset_attempts": reset_attempts,
                "requeued": count,
            },
            actor=_audit_actor(_principal),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        audit.log(
            action="outbox.requeue",
            status="failed",
            tenant_id=tenant_id,
            tenant_slug=resolved_slug,
            request_summary={"limit": limit, "reset_attempts": reset_attempts},
            error=str(exc),
            actor=_audit_actor(_principal),
        )
        db.commit()
        raise
    return {
        "ok": True,
        "tenant_slug": resolved_slug,
        "requeued": count,
        "reset_attempts": reset_attempts,
    }


@router.post("/admin/cleanup")
def cleanup_retention(
    payload: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
    _principal: AdminPrincipal = Depends(require_admin_action("admin.cleanup.run")),
) -> dict[str, Any]:
    payload = payload or {}
    dry_run = bool(payload.get("dry_run", True))
    audit = AdminAuditLogRepository(db)
    try:
        result = RetentionService(db).cleanup(dry_run=dry_run)
        audit.log(
            action="retention.cleanup",
            status="ok",
            request_summary=result,
            actor=_audit_actor(_principal),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        audit.log(
            action="retention.cleanup",
            status="failed",
            request_summary={"dry_run": dry_run},
            error=str(exc),
            actor=_audit_actor(_principal),
        )
        db.commit()
        raise
    return {"ok": True, **result}


@router.get("/admin/audit")
def get_admin_audit(
    tenant_slug: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _principal: AdminPrincipal = Depends(require_admin_action("admin.audit.read")),
) -> dict[str, Any]:
    tenant_id = None
    if tenant_slug:
        tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        tenant_id = tenant.id
    rows = AdminAuditLogRepository(db).list(
        tenant_id=tenant_id, tenant_slug=tenant_slug, limit=limit
    )
    return {
        "tenant_slug": tenant_slug,
        "audit": [
            {
                "id": str(r.id),
                "action": r.action,
                "tenant_id": str(r.tenant_id) if r.tenant_id else None,
                "tenant_slug": r.tenant_slug,
                "status": r.status,
                "request_summary": r.request_summary,
                "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


def _build_admin_stats(db: Session, *, tenant_id=None) -> dict[str, Any]:
    from app.repositories.webhook_event_repository import WebhookEventRepository

    outbox = OutboxRepository(db).stats(tenant_id=tenant_id)
    webhooks = WebhookEventRepository(db).stats()

    sync_stmt = select(SyncLog.status, func.count()).group_by(SyncLog.status)
    if tenant_id is not None:
        sync_stmt = sync_stmt.where(SyncLog.tenant_id == tenant_id)
    sync_rows = db.execute(sync_stmt).all()
    sync_logs = {str(status): int(count) for status, count in sync_rows}
    for key in ["ok", "failed", "running"]:
        sync_logs.setdefault(key, 0)

    oldest_dead_stmt = select(func.min(OutboxMessage.scheduled_at)).where(
        OutboxMessage.status == "dead"
    )
    if tenant_id is not None:
        oldest_dead_stmt = oldest_dead_stmt.where(OutboxMessage.tenant_id == tenant_id)
    oldest_dead = db.scalar(oldest_dead_stmt)

    return {
        "outbox": {**outbox, "oldest_dead_at": oldest_dead.isoformat() if oldest_dead else None},
        "webhooks": webhooks,
        "sync_logs": sync_logs,
    }


@router.get("/admin/stats")
def get_admin_stats(
    tenant_slug: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _principal: AdminPrincipal = Depends(require_admin_action("admin.stats.read")),
) -> dict[str, Any]:
    tenant_id = None
    if tenant_slug:
        tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        tenant_id = tenant.id
    stats = _build_admin_stats(db, tenant_id=tenant_id)
    return {"tenant_slug": tenant_slug, **stats}


@router.get("/admin/readiness")
def get_admin_readiness(
    tenant_slug: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _principal: AdminPrincipal = Depends(require_admin_action("admin.readiness.read")),
) -> dict[str, Any]:
    tenant_id = None
    tenant = None
    if tenant_slug:
        tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        tenant_id = tenant.id

    settings = get_settings()
    stats = _build_admin_stats(db, tenant_id=tenant_id)
    dead = int(stats["outbox"].get("dead", 0))
    failed = int(stats["outbox"].get("failed", 0))

    checks: dict[str, dict[str, Any]] = {
        "admin_secret_configured": {
            "ok": bool(settings.admin_sync_secret),
            "detail": "ADMIN_SYNC_SECRET is set" if settings.admin_sync_secret else "empty",
        },
        "admin_ip_allowlist_configured": {
            "ok": bool((settings.admin_allowed_ips or "").strip()),
            "detail": (
                "configured"
                if (settings.admin_allowed_ips or "").strip()
                else "empty (optional)"
            ),
        },
        "app_secret_not_default": {
            "ok": settings.app_secret_key != "change-me-in-production",
            "detail": (
                "custom"
                if settings.app_secret_key != "change-me-in-production"
                else "default"
            ),
        },
        "outbox_dead_empty": {
            "ok": dead == 0,
            "detail": f"dead={dead}, failed={failed}",
        },
        "retention_configured": {
            "ok": settings.retention_sent_outbox_days >= 0
            and settings.retention_processed_webhook_days >= 0
            and settings.retention_sync_log_days >= 0,
            "detail": (
                f"sent={settings.retention_sent_outbox_days},"
                f"processed_webhooks={settings.retention_processed_webhook_days},"
                f"sync_logs={settings.retention_sync_log_days}"
            ),
        },
    }
    if tenant is not None:
        checks["tenant_active"] = {
            "ok": tenant.status == "active",
            "detail": tenant.status,
        }

    required_ok = all(
        checks[k]["ok"]
        for k in [
            "admin_secret_configured",
            "app_secret_not_default",
            "outbox_dead_empty",
            "retention_configured",
        ]
    ) and (checks.get("tenant_active", {"ok": True})["ok"])
    return {
        "tenant_slug": tenant_slug,
        "ready": required_ok,
        "checks": checks,
        "stats": stats,
    }
