"""Тест эндпоинта проверки здоровья."""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check_returns_ok_status() -> None:
    """Health-check отвечает 200 и статусом ok."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
