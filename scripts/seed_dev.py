"""Seed development data for two test tenants."""

from __future__ import annotations

import hashlib

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalog import Master, Service, ServiceMaster
from app.models.tenant import Tenant
from app.models.tenant_link import TenantLink
from app.models.tenant_member import TenantMember

TENANT_A_SLUG = "salon-a"
TENANT_B_SLUG = "salon-b"


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def upsert_tenant(db, *, slug: str, display_name: str, booking_mode: str, timezone: str) -> Tenant:
    tenant = db.scalar(select(Tenant).where(Tenant.slug == slug))
    if tenant is None:
        tenant = Tenant(
            slug=slug,
            display_name=display_name,
            booking_mode=booking_mode,
            timezone=timezone,
            status="active",
        )
        db.add(tenant)
        db.flush()
    else:
        tenant.display_name = display_name
        tenant.booking_mode = booking_mode
        tenant.timezone = timezone
        tenant.status = "active"
    return tenant


def upsert_service(
    db, tenant: Tenant, *, external_key: str, name: str, price: int, duration: int
) -> Service:
    svc = db.scalar(
        select(Service).where(Service.tenant_id == tenant.id, Service.external_key == external_key)
    )
    if svc is None:
        svc = Service(
            tenant_id=tenant.id,
            external_key=external_key,
            name=name,
            price=price,
            price_type="fixed",
            duration_minutes=duration,
            buffer_minutes=0,
            is_active=True,
        )
        db.add(svc)
        db.flush()
    else:
        svc.name = name
        svc.price = price
        svc.duration_minutes = duration
        svc.is_active = True
    return svc


def upsert_master(db, tenant: Tenant, *, external_key: str, display_name: str) -> Master:
    master = db.scalar(
        select(Master).where(Master.tenant_id == tenant.id, Master.external_key == external_key)
    )
    if master is None:
        master = Master(
            tenant_id=tenant.id,
            external_key=external_key,
            display_name=display_name,
            is_active=True,
        )
        db.add(master)
        db.flush()
    else:
        master.display_name = display_name
        master.is_active = True
    return master


def ensure_service_master(db, tenant: Tenant, service: Service, master: Master) -> None:
    link = db.scalar(
        select(ServiceMaster).where(
            ServiceMaster.tenant_id == tenant.id,
            ServiceMaster.service_id == service.id,
            ServiceMaster.master_id == master.id,
        )
    )
    if link is None:
        db.add(
            ServiceMaster(
                tenant_id=tenant.id, service_id=service.id, master_id=master.id, is_active=True
            )
        )


def upsert_member(db, tenant: Tenant, *, max_user_id: int, role: str) -> None:
    member = db.scalar(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant.id, TenantMember.max_user_id == max_user_id
        )
    )
    if member is None:
        db.add(
            TenantMember(tenant_id=tenant.id, max_user_id=max_user_id, role=role, is_active=True)
        )
    else:
        member.role = role
        member.is_active = True


def upsert_link(
    db, tenant: Tenant, *, token: str, link_type: str, role_to_assign: str | None
) -> None:
    th = _token_hash(token)
    link = db.scalar(select(TenantLink).where(TenantLink.token_hash == th))
    if link is None:
        db.add(
            TenantLink(
                tenant_id=tenant.id,
                token_hash=th,
                link_type=link_type,
                role_to_assign=role_to_assign,
            )
        )


def seed() -> None:
    db = SessionLocal()
    try:
        tenant_a = upsert_tenant(
            db,
            slug=TENANT_A_SLUG,
            display_name="Салон A",
            booking_mode="request_only",
            timezone="Europe/Moscow",
        )
        tenant_b = upsert_tenant(
            db,
            slug=TENANT_B_SLUG,
            display_name="Салон B",
            booking_mode="request_only",
            timezone="Europe/Moscow",
        )

        a_s1 = upsert_service(
            db, tenant_a, external_key="manicure", name="Маникюр A", price=1500, duration=60
        )
        a_s2 = upsert_service(
            db, tenant_a, external_key="haircut", name="Стрижка A", price=2000, duration=45
        )
        b_s1 = upsert_service(
            db, tenant_b, external_key="massage", name="Массаж B", price=3000, duration=90
        )
        b_s2 = upsert_service(
            db, tenant_b, external_key="brows", name="Брови B", price=1200, duration=30
        )

        a_m1 = upsert_master(db, tenant_a, external_key="anna", display_name="Анна A")
        a_m2 = upsert_master(db, tenant_a, external_key="olga", display_name="Ольга A")
        b_m1 = upsert_master(db, tenant_b, external_key="boris", display_name="Борис B")
        b_m2 = upsert_master(db, tenant_b, external_key="bella", display_name="Белла B")

        for m in [a_m1, a_m2]:
            ensure_service_master(db, tenant_a, a_s1, m)
        ensure_service_master(db, tenant_a, a_s2, a_m2)
        ensure_service_master(db, tenant_b, b_s1, b_m1)
        ensure_service_master(db, tenant_b, b_s2, b_m1)
        ensure_service_master(db, tenant_b, b_s2, b_m2)

        upsert_member(db, tenant_a, max_user_id=900001, role="owner")
        upsert_member(db, tenant_b, max_user_id=900002, role="owner")

        upsert_link(
            db, tenant_a, token="tenant-a-client-token", link_type="client", role_to_assign=None
        )
        upsert_link(
            db, tenant_b, token="tenant-b-client-token", link_type="client", role_to_assign=None
        )
        upsert_link(
            db, tenant_a, token="tenant-a-owner-token", link_type="owner", role_to_assign="owner"
        )
        upsert_link(
            db, tenant_b, token="tenant-b-owner-token", link_type="owner", role_to_assign="owner"
        )

        db.commit()
        print(f"Seeded tenants: {tenant_a.slug}, {tenant_b.slug}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    seed()


if __name__ == "__main__":
    main()
