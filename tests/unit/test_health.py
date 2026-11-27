def test_root_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_live_health(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_health(client):
    class FakeDB:
        def execute(self, *_args, **_kwargs):
            return 1

    class FakeRedis:
        def ping(self):
            return True

        def close(self):
            return None

    from app.core.config import get_settings
    from app.db.session import get_db

    app = client.app
    app.dependency_overrides[get_db] = lambda: FakeDB()
    settings = get_settings()
    original_from_url = __import__("redis").Redis.from_url
    __import__("redis").Redis.from_url = lambda *_a, **_k: FakeRedis()
    try:
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        response = client.get("/ready")
        assert response.status_code == 200
    finally:
        __import__("redis").Redis.from_url = original_from_url
        app.dependency_overrides.clear()
        _ = settings
