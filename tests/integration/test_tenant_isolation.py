import pytest
from sqlalchemy.exc import IntegrityError

from app.models.booking import Booking
from app.models.catalog import Master, Service, ServiceMaster
from app.models.tenant import Tenant
from app.repositories.booking_repository import BookingRepository
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.dialog_session_repository import DialogSessionRepository

pytestmark = pytest.mark.integration


def _make_tenant(slug: str, name: str) -> Tenant:
    return Tenant(
        slug=slug,
        display_name=name,
        status="active",
        timezone="Europe/Moscow",
        booking_mode="request_only",
    )


def _make_service(tenant_id, external_key: str, name: str, price: int, duration: int) -> Service:
    return Service(
        tenant_id=tenant_id,
        external_key=external_key,
        name=name,
        price=price,
        price_type="fixed",
        duration_minutes=duration,
        buffer_minutes=0,
        is_active=True,
    )


def test_tenant_catalog_isolation(db_session):
    t1 = _make_tenant("a", "A")
    t2 = _make_tenant("b", "B")
    db_session.add_all([t1, t2])
    db_session.flush()

    s1 = _make_service(t1.id, "svc", "Svc A", 100, 30)
    s2 = _make_service(t2.id, "svc", "Svc B", 200, 60)
    m1 = Master(tenant_id=t1.id, external_key="m", display_name="Master A", is_active=True)
    m2 = Master(tenant_id=t2.id, external_key="m", display_name="Master B", is_active=True)
    db_session.add_all([s1, s2, m1, m2])
    db_session.flush()

    repo = CatalogRepository(db_session)
    a_services = repo.list_active_services(t1.id)
    b_services = repo.list_active_services(t2.id)
    assert [s.name for s in a_services] == ["Svc A"]
    assert [s.name for s in b_services] == ["Svc B"]

    assert repo.get_service(t1.id, s2.id) is None
    assert repo.get_service(t2.id, s1.id) is None


def test_service_master_composite_fk_blocks_cross_tenant_link(db_session):
    t1 = _make_tenant("a2", "A2")
    t2 = _make_tenant("b2", "B2")
    db_session.add_all([t1, t2])
    db_session.flush()

    s1 = _make_service(t1.id, "svc1", "Svc1", 100, 30)
    m2 = Master(tenant_id=t2.id, external_key="m2", display_name="M2", is_active=True)
    db_session.add_all([s1, m2])
    db_session.flush()

    db_session.add(
        ServiceMaster(tenant_id=t1.id, service_id=s1.id, master_id=m2.id, is_active=True)
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_booking_repository_tenant_scoping(db_session):
    t1 = _make_tenant("a3", "A3")
    t2 = _make_tenant("b3", "B3")
    db_session.add_all([t1, t2])
    db_session.flush()

    s1 = _make_service(t1.id, "svc", "Svc A", 100, 30)
    s2 = _make_service(t2.id, "svc", "Svc B", 200, 30)
    db_session.add_all([s1, s2])
    db_session.flush()

    repo = BookingRepository(db_session)
    b1 = repo.create(
        Booking(
            tenant_id=t1.id,
            max_user_id=100,
            chat_id=1000,
            service_id=s1.id,
            status="awaiting_salon",
            booking_mode="request_only",
        )
    )
    b2 = repo.create(
        Booking(
            tenant_id=t2.id,
            max_user_id=100,
            chat_id=1000,
            service_id=s2.id,
            status="awaiting_salon",
            booking_mode="request_only",
        )
    )
    db_session.commit()

    assert repo.get(t1.id, b2.id) is None
    assert repo.get(t2.id, b1.id) is None
    assert [b.id for b in repo.list_for_user(t1.id, 100)] == [b1.id]
    assert [b.id for b in repo.list_for_user(t2.id, 100)] == [b2.id]



def test_booking_composite_fk_blocks_cross_tenant_service(db_session):
    t1 = _make_tenant("a5", "A5")
    t2 = _make_tenant("b5", "B5")
    db_session.add_all([t1, t2])
    db_session.flush()

    s2 = _make_service(t2.id, "svc2", "Svc B5", 200, 30)
    db_session.add(s2)
    db_session.flush()

    db_session.add(
        Booking(
            tenant_id=t1.id,
            max_user_id=100,
            chat_id=1000,
            service_id=s2.id,
            status="awaiting_salon",
            booking_mode="request_only",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_booking_composite_fk_blocks_cross_tenant_master(db_session):
    t1 = _make_tenant("a6", "A6")
    t2 = _make_tenant("b6", "B6")
    db_session.add_all([t1, t2])
    db_session.flush()

    s1 = _make_service(t1.id, "svc1", "Svc A6", 100, 30)
    m2 = Master(tenant_id=t2.id, external_key="m2", display_name="M2", is_active=True)
    db_session.add_all([s1, m2])
    db_session.flush()

    db_session.add(
        Booking(
            tenant_id=t1.id,
            max_user_id=100,
            chat_id=1000,
            service_id=s1.id,
            master_id=m2.id,
            status="awaiting_salon",
            booking_mode="request_only",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

def test_dialog_session_tracks_current_tenant(db_session):
    t1 = _make_tenant("a4", "A4")
    t2 = _make_tenant("b4", "B4")
    db_session.add_all([t1, t2])
    db_session.flush()

    repo = DialogSessionRepository(db_session)
    repo.upsert_current_tenant(chat_id=777, max_user_id=42, tenant_id=t1.id)
    db_session.commit()
    assert repo.get_current_tenant_id(777) == t1.id

    repo.upsert_current_tenant(chat_id=777, max_user_id=42, tenant_id=t2.id)
    db_session.commit()
    assert repo.get_current_tenant_id(777) == t2.id