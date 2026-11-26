def test_webhook_max_accepts_payload_without_secret(client):
    response = client.post("/webhook/max", json={"update_type": "message_created"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_webhook_max_rejects_invalid_secret(client, monkeypatch):
    monkeypatch.setenv("MAX_WEBHOOK_SECRET", "expected-secret")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        response = client.post(
            "/webhook/max",
            json={"update_type": "message_created"},
            headers={"X-Max-Bot-Api-Secret": "wrong"},
        )
        assert response.status_code == 401
    finally:
        get_settings.cache_clear()
