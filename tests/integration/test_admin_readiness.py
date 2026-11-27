import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import get_db
from app.main import create_app
from app.models.tenant import Tenant

pytestmark = pytest.mark.integration


def _client(db_session, monkeypatch):
    monkeypatch.setenv("ADMIN_SYNC_SECRET", "sec")
    monkeypatch.setenv("APP_SECRET_KEY", "not-default")
    get_settings.cache_clear()
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), {"X-Admin-Sync-Secret": "sec"}


def test_admin_readiness_reports_checks(db_session, monkeypatch):
    tenant = Tenant(slug="ready-a", display_name="Ready A", status="active")
    db_session.add(tenant)
    db_session.commit()

    client, headers = _client(db_session, monkeypatch)
    r = client.get("/admin/readiness?tenant_slug=ready-a", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_slug"] == "ready-a"
    assert body["ready"] is True
    assert body["checks"]["admin_secret_configured"]["ok"] is True
    assert body["checks"]["outbox_dead_empty"]["ok"] is True
    assert "stats" in body
    get_settings.cache_clear()
