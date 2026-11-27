import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import create_app
from app.models.catalog import Master, Service, ServiceMaster
from app.models.sync_log import SyncLog
from app.models.tenant import Tenant

pytestmark = pytest.mark.integration


def _client_with_db(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_csv_catalog_sync_idempotent_and_tenant_scoped(db_session):
    t1 = Tenant(slug="salon-sync-a", display_name="A", status="active")
    t2 = Tenant(slug="salon-sync-b", display_name="B", status="active")
    db_session.add_all([t1, t2])
    db_session.commit()

    client = _client_with_db(db_session)
    catalog = {
        "services": [
            {
                "external_key": "svc1",
                "name": "Cut",
                "price": 1000,
                "price_type": "fixed",
                "duration_minutes": 60,
                "buffer_minutes": 0,
                "is_active": True,
            }
        ],
        "masters": [{"external_key": "m1", "display_name": "Anna", "is_active": True}],
        "service_masters": [
            {"service_external_key": "svc1", "master_external_key": "m1", "is_active": True}
        ],
        "master_working_hours": [],
        "schedule_exceptions": [],
    }

    r = client.post("/admin/sync/salon-sync-a/csv", json={"base_dir": "x", "catalog": catalog})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    # second sync same catalog - idempotent upsert, no duplicates
    r = client.post("/admin/sync/salon-sync-a/csv", json={"base_dir": "x", "catalog": catalog})
    assert r.status_code == 200

    assert db_session.query(Service).filter_by(tenant_id=t1.id).count() == 1
    assert db_session.query(Master).filter_by(tenant_id=t1.id).count() == 1
    assert db_session.query(ServiceMaster).filter_by(tenant_id=t1.id).count() == 1
    assert db_session.query(Service).filter_by(tenant_id=t2.id).count() == 0
    assert db_session.query(SyncLog).filter_by(tenant_id=t1.id).count() >= 2

    # deactivate missing
    catalog2 = {"services": [], "masters": [], "service_masters": []}
    r = client.post("/admin/sync/salon-sync-a/csv", json={"base_dir": "x", "catalog": catalog2})
    assert r.status_code == 200
    svc = db_session.query(Service).filter_by(tenant_id=t1.id).one()
    assert svc.is_active is False
