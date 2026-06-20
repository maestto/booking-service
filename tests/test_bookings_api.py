"""Тесты REST API: создание, получение, список, отмена и ограничение частоты."""

from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core import rate_limit
from app.db.session import get_db
from app.main import app
from app.models import Booking, BookingStatus


@pytest.fixture()
def test_client(
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, sessionmaker], None, None]:
    def override_get_db() -> Generator:
        db = session_factory()

        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr("app.api.bookings.enqueue_booking_processing", lambda booking_id: None)
    monkeypatch.setattr(
        rate_limit,
        "bookings_rate_limiter",
        rate_limit.InMemoryRateLimiter(limit=60, window_seconds=60),
    )

    with TestClient(app) as client:
        yield client, session_factory

    app.dependency_overrides.clear()


def booking_payload(
    name: str = "Alex",
    service_type: str = "consultation",
) -> dict[str, str]:
    return {
        "name": name,
        "datetime": "2026-07-01T10:30:00+00:00",
        "service_type": service_type,
    }


def create_booking(client: TestClient, **overrides: str) -> dict:
    payload = booking_payload(**overrides)
    response = client.post("/bookings", json=payload)

    assert response.status_code == 201

    return response.json()


def test_create_booking_returns_pending_booking(test_client) -> None:
    """POST создаёт бронь и отдаёт её в статусе pending."""
    client, _ = test_client

    data = create_booking(client)

    assert data["id"] == 1
    assert data["name"] == "Alex"
    assert data["service_type"] == "consultation"
    assert data["status"] == "pending"
    assert data["created_at"] is not None
    assert data["updated_at"] is not None


def test_create_booking_enqueues_processing_task(test_client, monkeypatch: pytest.MonkeyPatch) -> None:
    """После создания брони задача уходит в очередь."""
    client, _ = test_client
    enqueued_booking_ids = []

    monkeypatch.setattr("app.api.bookings.enqueue_booking_processing", enqueued_booking_ids.append)

    data = create_booking(client)

    assert enqueued_booking_ids == [data["id"]]


def test_get_booking_by_id(test_client) -> None:
    """GET по id возвращает нужную бронь."""
    client, _ = test_client
    created = create_booking(client, name="Maria")

    response = client.get(f"/bookings/{created['id']}")

    assert response.status_code == 200
    assert response.json()["name"] == "Maria"


def test_get_missing_booking_returns_404(test_client) -> None:
    """GET несуществующей брони отдаёт 404."""
    client, _ = test_client

    response = client.get("/bookings/999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Booking not found"


def test_list_bookings_returns_created_bookings(test_client) -> None:
    """Список возвращает созданные брони по порядку."""
    client, _ = test_client
    create_booking(client, name="Alex")
    create_booking(client, name="Maria")

    response = client.get("/bookings")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Alex", "Maria"]


def test_list_bookings_supports_status_filter(test_client) -> None:
    """Список умеет фильтровать брони по статусу."""
    client, testing_session = test_client
    pending = create_booking(client, name="Pending")
    failed = create_booking(client, name="Failed")

    with testing_session() as db:
        booking = db.get(Booking, failed["id"])
        booking.status = BookingStatus.FAILED
        db.commit()

    response = client.get("/bookings", params={"status": "failed"})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [failed["id"]]
    assert pending["id"] not in [item["id"] for item in response.json()]


def test_list_bookings_supports_pagination(test_client) -> None:
    """Список поддерживает limit и offset."""
    client, _ = test_client
    create_booking(client, name="First")
    create_booking(client, name="Second")
    create_booking(client, name="Third")

    response = client.get("/bookings", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Second"]


def test_cancel_pending_booking(test_client) -> None:
    """Отмена брони в статусе pending переводит её в cancelled."""
    client, _ = test_client
    created = create_booking(client)

    response = client.delete(f"/bookings/{created['id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_non_pending_booking_returns_400(test_client) -> None:
    """Нельзя отменить бронь не в статусе pending, в ответ 400."""
    client, testing_session = test_client
    created = create_booking(client)

    with testing_session() as db:
        booking = db.get(Booking, created["id"])
        booking.status = BookingStatus.CONFIRMED
        db.commit()

    response = client.delete(f"/bookings/{created['id']}")

    assert response.status_code == 400
    assert response.json()["detail"] == "Only pending bookings can be cancelled"


def test_create_booking_rejects_invalid_payload(test_client) -> None:
    """Пустое имя в запросе отклоняется с 422."""
    client, _ = test_client
    payload = booking_payload()
    payload["name"] = ""

    response = client.post("/bookings", json=payload)

    assert response.status_code == 422


def test_create_booking_returns_429_when_rate_limit_is_exceeded(
    test_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """При превышении лимита POST отдаёт 429."""
    client, _ = test_client
    monkeypatch.setattr(
        rate_limit,
        "bookings_rate_limiter",
        rate_limit.InMemoryRateLimiter(limit=1, window_seconds=60),
    )

    first_response = client.post("/bookings", json=booking_payload(name="First"))
    second_response = client.post("/bookings", json=booking_payload(name="Second"))

    assert first_response.status_code == 201
    assert second_response.status_code == 429
    assert second_response.json()["detail"] == "Too many booking requests"
    assert int(second_response.headers["Retry-After"]) > 0


def test_list_bookings_rejects_invalid_status_filter(test_client) -> None:
    """Неизвестный статус в фильтре отклоняется с 422."""
    client, _ = test_client

    response = client.get("/bookings", params={"status": "unknown"})

    assert response.status_code == 422
