import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.session import get_db
from app.main import create_app
from app.models.tenant import Tenant

pytestmark = pytest.mark.integration


def _client(db_session, monkeypatch, *, rbac=False):
    monkeypatch.setenv("ADMIN_SYNC_SECRET", "sec")
    monkeypatch.setenv("ADMIN_RBAC_ENABLED", "true" if rbac else "false")
    get_settings.cache_clear()
    app = create_app()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_rbac_scaffold_disabled_keeps_shared_secret_behavior(db_session, monkeypatch):
    db_session.add(Tenant(slug="rbac-a", display_name="RBAC A", status="active"))
    db_session.commit()
    client = _client(db_session, monkeypatch, rbac=False)

    r = client.get("/admin/stats?tenant_slug=rbac-a", headers={"X-Admin-Sync-Secret": "sec"})
    assert r.status_code == 200
    get_settings.cache_clear()


def test_rbac_scaffold_enforces_role_actions(db_session, monkeypatch):
    db_session.add(Tenant(slug="rbac-b", display_name="RBAC B", status="active"))
    db_session.commit()
    client = _client(db_session, monkeypatch, rbac=True)
    headers = {"X-Admin-Sync-Secret": "sec", "X-Admin-Role": "ops_viewer"}

    ok = client.get("/admin/stats?tenant_slug=rbac-b", headers=headers)
    assert ok.status_code == 200

    audit = client.get("/admin/audit?tenant_slug=rbac-b&limit=10", headers=headers)
    assert audit.status_code == 200

    denied = client.post("/admin/cleanup", json={"dry_run": True}, headers=headers)
    assert denied.status_code == 403

    bad_role = client.get(
        "/admin/stats?tenant_slug=rbac-b",
        headers={"X-Admin-Sync-Secret": "sec", "X-Admin-Role": "unknown"},
    )
    assert bad_role.status_code == 403
    get_settings.cache_clear()
