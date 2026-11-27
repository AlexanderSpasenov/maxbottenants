from app.main import create_app


def test_request_id_header_generated_and_echoed():
    app = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    r = client.get("/health/live")
    assert r.status_code == 200
    assert "X-Request-ID" in r.headers
    assert r.headers["X-Request-ID"]


def test_request_id_header_passthrough():
    app = create_app()
    from fastapi.testclient import TestClient

    client = TestClient(app)
    r = client.get("/health/live", headers={"X-Request-ID": "req-123"})
    assert r.status_code == 200
    assert r.headers["X-Request-ID"] == "req-123"
