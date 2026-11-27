import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import create_app
from app.models.catalog import Master, Service, ServiceMaster
from app.models.tenant import Tenant
from app.models.tenant_link import TenantLink
from app.repositories.tenant_link_repository import hash_token
from app.workers.event_worker import process_pending_events

pytestmark = pytest.mark.integration


def _client_with_db(db_session):
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_callback_payload_routed_as_text(db_session):
    t = Tenant(slug="salon-cb", display_name="Salon CB", status="active")
    db_session.add(t)
    db_session.flush()
    s = Service(
        tenant_id=t.id, external_key="svc1", name="Svc", price=1000,
        price_type="fixed", duration_minutes=60, buffer_minutes=0, is_active=True,
    )
    m = Master(tenant_id=t.id, external_key="m1", display_name="M", is_active=True)
    db_session.add_all([s, m])
    db_session.flush()
    db_session.add(ServiceMaster(tenant_id=t.id, service_id=s.id, master_id=m.id, is_active=True))
    db_session.add(TenantLink(tenant_id=t.id, token_hash=hash_token("cb-token"), link_type="client"))
    db_session.commit()

    client = _client_with_db(db_session)
    # start via message
    r = client.post("/webhook/max", json={
        "update_type": "message_created",
        "timestamp": 1,
        "message": {
            "mid": "m1", "chat_id": 100, "sender": {"user_id": 200, "name": "T"},
            "body": {"text": "/start cb-token"},
        },
    })
    assert r.status_code == 200

    # callback variant: payload as text choice
    r = client.post("/webhook/max", json={
        "update_type": "message_callback",
        "timestamp": 2,
        "callback": {"callback_id": "cb1", "chat_id": 100, "user_id": 200, "payload": "1"},
    })
    assert r.status_code == 200
    process_pending_events(batch_size=50, db=db_session)
