from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.integrations.sheets.csv_source import CsvCatalogSource
from app.models.tenant import Tenant
from app.services.sync.catalog_sync import CatalogSyncService

router = APIRouter(tags=["admin-sync"])


@router.post("/admin/sync/{tenant_slug}/csv")
async def sync_tenant_csv(
    tenant_slug: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    base_dir = str(payload.get("base_dir") or "").strip()
    if not base_dir:
        raise HTTPException(status_code=400, detail="base_dir is required")

    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    source = CsvCatalogSource(base_dir)
    catalog = await source.fetch_tenant_catalog(str(tenant.id))
    # allow caller to pass normalized catalog directly (fixture/testing)
    if isinstance(payload.get("catalog"), dict):
        catalog = payload["catalog"]

    log = CatalogSyncService(db).sync_tenant_catalog(tenant.id, catalog)
    return {
        "ok": log.status == "ok",
        "tenant_slug": tenant_slug,
        "status": log.status,
        "services_upserted": log.services_upserted,
        "masters_upserted": log.masters_upserted,
        "schedule_rows_upserted": log.schedule_rows_upserted,
        "deactivated": log.deactivated,
        "error": log.error_message,
    }
