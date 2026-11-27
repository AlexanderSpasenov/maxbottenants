from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Master, Service, ServiceMaster
from app.models.schedule import MasterWorkingHours, ScheduleException
from app.models.sync_log import SyncLog
from app.models.tenant import Tenant


@dataclass
class SyncResult:
    services_upserted: int = 0
    masters_upserted: int = 0
    schedule_rows_upserted: int = 0
    deactivated: int = 0


SYNC_MODES = {"full", "upsert_only"}


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "active"}


class CatalogSyncService:
    def __init__(self, db: Session):
        self.db = db

    def sync_tenant_catalog(
        self, tenant_id: uuid.UUID, catalog: dict[str, Any], *, mode: str = "upsert_only"
    ) -> SyncLog:
        tenant = self.db.get(Tenant, tenant_id)
        if tenant is None:
            raise ValueError("Tenant not found")
        if mode not in SYNC_MODES:
            raise ValueError(f"Invalid sync mode: {mode}")

        log = SyncLog(tenant_id=tenant_id, started_at=datetime.now(UTC), status="running")
        self.db.add(log)
        self.db.flush()
        try:
            result = self._apply(tenant, catalog, mode=mode)
            log.status = "ok"
            log.services_upserted = result.services_upserted
            log.masters_upserted = result.masters_upserted
            log.schedule_rows_upserted = result.schedule_rows_upserted
            log.deactivated = result.deactivated
            log.finished_at = datetime.now(UTC)
            tenant.last_synced_at = log.finished_at
            tenant.last_sync_status = "ok"
            tenant.last_sync_error = None
            self.db.add_all([log, tenant])
            self.db.commit()
            self.db.refresh(log)
            return log
        except Exception as exc:
            self.db.rollback()
            fail = SyncLog(
                tenant_id=tenant_id,
                started_at=log.started_at,
                finished_at=datetime.now(UTC),
                status="failed",
                error_message=str(exc)[:4000],
            )
            tenant.last_synced_at = fail.finished_at
            tenant.last_sync_status = "failed"
            tenant.last_sync_error = fail.error_message
            self.db.add_all([fail, tenant])
            self.db.commit()
            self.db.refresh(fail)
            return fail

    def _apply(self, tenant: Tenant, catalog: dict[str, Any], *, mode: str) -> SyncResult:
        res = SyncResult()
        services_in = catalog.get("services") or []
        masters_in = catalog.get("masters") or []
        links_in = catalog.get("service_masters") or []
        hours_in = catalog.get("master_working_hours") or []
        exceptions_in = catalog.get("schedule_exceptions") or []
        for name, rows in [
            ("services", services_in),
            ("masters", masters_in),
            ("service_masters", links_in),
            ("master_working_hours", hours_in),
            ("schedule_exceptions", exceptions_in),
        ]:
            if not isinstance(rows, list):
                raise ValueError(f"{name} must be a list")
            for i, row in enumerate(rows):
                if not isinstance(row, dict):
                    raise ValueError(f"{name}[{i}] must be an object")

        service_map: dict[str, Service] = {}
        seen_services: set[str] = set()
        for row in services_in:
            key = str(row.get("external_key") or "").strip()
            if not key:
                continue
            seen_services.add(key)
            svc = self.db.scalar(
                select(Service).where(Service.tenant_id == tenant.id, Service.external_key == key)
            )
            if svc is None:
                svc = Service(
                    tenant_id=tenant.id,
                    external_key=key,
                    name=str(row.get("name") or key),
                )
                self.db.add(svc)
                res.services_upserted += 1
            svc.name = str(row.get("name") or svc.name)
            svc.price = row.get("price")
            svc.price_type = str(row.get("price_type") or svc.price_type or "fixed")
            svc.duration_minutes = int(row.get("duration_minutes") or svc.duration_minutes or 60)
            svc.buffer_minutes = int(row.get("buffer_minutes") or 0)
            svc.is_active = _as_bool(row.get("is_active"), True)
            self.db.add(svc)
            service_map[key] = svc

        master_map: dict[str, Master] = {}
        seen_masters: set[str] = set()
        for row in masters_in:
            key = str(row.get("external_key") or "").strip()
            if not key:
                continue
            seen_masters.add(key)
            m = self.db.scalar(
                select(Master).where(Master.tenant_id == tenant.id, Master.external_key == key)
            )
            if m is None:
                m = Master(
                    tenant_id=tenant.id,
                    external_key=key,
                    display_name=str(row.get("display_name") or key),
                )
                self.db.add(m)
                res.masters_upserted += 1
            m.display_name = str(row.get("display_name") or m.display_name)
            m.is_active = _as_bool(row.get("is_active"), True)
            self.db.add(m)
            master_map[key] = m

        self.db.flush()

        seen_links: set[tuple[uuid.UUID, uuid.UUID]] = set()
        for row in links_in:
            sk = str(row.get("service_external_key") or "").strip()
            mk = str(row.get("master_external_key") or "").strip()
            svc = service_map.get(sk) or self.db.scalar(
                select(Service).where(Service.tenant_id == tenant.id, Service.external_key == sk)
            )
            mst = master_map.get(mk) or self.db.scalar(
                select(Master).where(Master.tenant_id == tenant.id, Master.external_key == mk)
            )
            if not svc or not mst:
                continue
            seen_links.add((svc.id, mst.id))
            link = self.db.scalar(
                select(ServiceMaster).where(
                    ServiceMaster.tenant_id == tenant.id,
                    ServiceMaster.service_id == svc.id,
                    ServiceMaster.master_id == mst.id,
                )
            )
            if link is None:
                link = ServiceMaster(tenant_id=tenant.id, service_id=svc.id, master_id=mst.id)
                self.db.add(link)
            link.is_active = _as_bool(row.get("is_active"), True)
            self.db.add(link)

        # deactivate missing only in explicit full snapshot mode
        if mode == "full":
            for svc in self.db.scalars(select(Service).where(Service.tenant_id == tenant.id)):
                if svc.external_key not in seen_services and svc.is_active:
                    svc.is_active = False
                    self.db.add(svc)
                    res.deactivated += 1
            for m in self.db.scalars(select(Master).where(Master.tenant_id == tenant.id)):
                if m.external_key not in seen_masters and m.is_active:
                    m.is_active = False
                    self.db.add(m)
                    res.deactivated += 1
            for link in self.db.scalars(
                select(ServiceMaster).where(ServiceMaster.tenant_id == tenant.id)
            ):
                if (link.service_id, link.master_id) not in seen_links and link.is_active:
                    link.is_active = False
                    self.db.add(link)
                    res.deactivated += 1

        # Replace schedule rows for simplicity/idempotency (tenant-scoped)
        for row in self.db.scalars(
            select(MasterWorkingHours).where(MasterWorkingHours.tenant_id == tenant.id)
        ):
            self.db.delete(row)
        for row in self.db.scalars(
            select(ScheduleException).where(ScheduleException.tenant_id == tenant.id)
        ):
            self.db.delete(row)
        self.db.flush()

        for row in hours_in:
            mk = str(row.get("master_external_key") or "").strip()
            master_id = None
            if mk:
                mst = master_map.get(mk) or self.db.scalar(
                    select(Master).where(Master.tenant_id == tenant.id, Master.external_key == mk)
                )
                master_id = mst.id if mst else None
            wh = MasterWorkingHours(
                tenant_id=tenant.id,
                master_id=master_id,
                weekday=int(row.get("weekday")),
                start_time=row.get("start_time"),
                end_time=row.get("end_time"),
                is_working=_as_bool(row.get("is_working"), True),
            )
            self.db.add(wh)
            res.schedule_rows_upserted += 1
        for row in exceptions_in:
            mk = str(row.get("master_external_key") or "").strip()
            master_id = None
            if mk:
                mst = master_map.get(mk) or self.db.scalar(
                    select(Master).where(Master.tenant_id == tenant.id, Master.external_key == mk)
                )
                master_id = mst.id if mst else None
            ex = ScheduleException(
                tenant_id=tenant.id,
                master_id=master_id,
                date=row.get("date"),
                start_time=row.get("start_time"),
                end_time=row.get("end_time"),
                type=str(row.get("type") or "blocked"),
                comment=row.get("comment"),
            )
            self.db.add(ex)
            res.schedule_rows_upserted += 1

        self.db.flush()
        return res
