import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import get_db
from app.main import create_app
from app.models.tenant import Tenant

pytestmark = pytest.mark.integration


def _client(db_session, monkeypatch, secret="sec", allowed_ips=""):
    monkeypatch.setenv("ADMIN_SYNC_SECRET", secret)
    monkeypatch.setenv("ADMIN_ALLOWED_IPS", allowed_ips)
    get_settings.cache_clear()
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), {"X-Admin-Sync-Secret": secret}


def test_admin_ip_allowlist_blocks_and_allows(db_session, monkeypatch):
    tenant = Tenant(slug="ip-a", display_name="IP A", status="active")
    db_session.add(tenant)
    db_session.commit()

    client, headers = _client(db_session, monkeypatch, allowed_ips="10.0.0.1")
    r = client.get("/admin/stats?tenant_slug=ip-a", headers=headers)
    assert r.status_code == 403

    get_settings.cache_clear()
    client, headers = _client(db_session, monkeypatch, allowed_ips="testclient,10.0.0.1")
    r = client.get("/admin/stats?tenant_slug=ip-a", headers=headers)
    assert r.status_code == 200
    get_settings.cache_clear()
