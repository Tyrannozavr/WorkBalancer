from fastapi.testclient import TestClient

from workbalancer.main import app


def test_health_returns_ok() -> None:
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_ready_without_db_may_fail() -> None:
    """Без PostgreSQL /health/ready возвращает 503 — допустимо в unit-окружении."""
    with TestClient(app) as client:
        r = client.get("/health/ready")
    assert r.status_code in (200, 503)
