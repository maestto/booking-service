"""Тесты воркера: подтверждение, повторы, идемпотентность и перевод в failed."""

import datetime as dt

import pytest
from sqlalchemy.orm import sessionmaker

from app.models import Booking, BookingStatus
from app.services.external_booking import ExternalBookingServiceError
from app.worker import tasks


@pytest.fixture()
def testing_session(
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> sessionmaker:
    monkeypatch.setattr(tasks, "SessionLocal", session_factory)
    return session_factory


def create_booking(
    session_factory: sessionmaker,
    status: BookingStatus = BookingStatus.PENDING,
) -> Booking:
    with session_factory() as db:
        booking = Booking(
            name="Alex",
            datetime=dt.datetime(2026, 7, 1, 10, 30, tzinfo=dt.timezone.utc),
            service_type="consultation",
            status=status,
        )

        db.add(booking)
        db.commit()
        db.refresh(booking)

        return booking


def test_process_booking_confirms_booking_and_sends_notification(
    testing_session: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Успешная обработка переводит бронь в confirmed и шлёт уведомление."""
    booking = create_booking(testing_session)
    sent_notifications = []

    monkeypatch.setattr(tasks, "confirm_booking", lambda booking_id: None)
    monkeypatch.setattr(tasks, "send_mock_notification", sent_notifications.append)

    result = tasks.process_booking_logic(booking.id)

    with testing_session() as db:
        updated_booking = db.get(Booking, booking.id)

        assert result == BookingStatus.CONFIRMED
        assert updated_booking.status == BookingStatus.CONFIRMED
        assert sent_notifications[0].id == booking.id


def test_process_booking_keeps_booking_pending_when_external_service_fails_before_retry(
    testing_session: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Если мок-сервис упал, бронь остаётся pending и уведомление не уходит."""
    booking = create_booking(testing_session)
    sent_notifications = []

    def fail_confirmation(booking_id: int) -> None:
        raise ExternalBookingServiceError("External service failed")

    monkeypatch.setattr(tasks, "confirm_booking", fail_confirmation)
    monkeypatch.setattr(tasks, "send_mock_notification", sent_notifications.append)

    with pytest.raises(ExternalBookingServiceError):
        tasks.process_booking_logic(booking.id)

    with testing_session() as db:
        updated_booking = db.get(Booking, booking.id)

        assert updated_booking.status == BookingStatus.PENDING
        assert sent_notifications == []


def test_process_booking_returns_none_when_booking_is_missing(
    testing_session: sessionmaker,
) -> None:
    """Для несуществующей брони задача просто возвращает None."""
    result = tasks.process_booking_logic(booking_id=999)

    assert result is None


# Воркер не трогает бронь не в статусе pending.
# Саму гонку (SELECT ... FOR UPDATE) тут не проверяем. Тесты идут на SQLite ради
# простоты, а в проде такое тестируют на PostgreSQL с потоками и таймингами.
@pytest.mark.parametrize(
    "initial_status",
    [
        BookingStatus.CONFIRMED,
        BookingStatus.FAILED,
        BookingStatus.CANCELLED,
    ],
)
def test_process_booking_skips_non_pending_booking(
    testing_session: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
    initial_status: BookingStatus,
) -> None:
    """Бронь не в статусе pending воркер пропускает, статус и уведомления не трогает."""
    booking = create_booking(testing_session, status=initial_status)
    sent_notifications = []
    confirmation_calls = []

    def confirm(booking_id: int) -> None:
        confirmation_calls.append(booking_id)

    monkeypatch.setattr(tasks, "confirm_booking", confirm)
    monkeypatch.setattr(tasks, "send_mock_notification", sent_notifications.append)

    result = tasks.process_booking_logic(booking.id)

    with testing_session() as db:
        updated_booking = db.get(Booking, booking.id)

        assert result == initial_status
        assert updated_booking.status == initial_status
        assert confirmation_calls == []
        assert sent_notifications == []


def test_mark_booking_failed_after_retries_are_exhausted(
    testing_session: sessionmaker,
) -> None:
    """После исчерпания попыток бронь переводится в failed."""
    booking = create_booking(testing_session)

    result = tasks.mark_booking_failed(booking.id)

    with testing_session() as db:
        updated_booking = db.get(Booking, booking.id)

        assert result == BookingStatus.FAILED
        assert updated_booking.status == BookingStatus.FAILED


def test_mark_booking_failed_keeps_non_pending_booking_unchanged(
    testing_session: sessionmaker,
) -> None:
    """Перевод в failed не трогает бронь, которая уже не pending."""
    booking = create_booking(testing_session, status=BookingStatus.CANCELLED)

    result = tasks.mark_booking_failed(booking.id)

    with testing_session() as db:
        updated_booking = db.get(Booking, booking.id)

        assert result == BookingStatus.CANCELLED
        assert updated_booking.status == BookingStatus.CANCELLED


def test_retry_countdown_uses_exponential_backoff() -> None:
    """Задержка между попытками растёт как 2, 4 и 8 секунд."""
    assert tasks.get_retry_countdown(0) == 2
    assert tasks.get_retry_countdown(1) == 4
    assert tasks.get_retry_countdown(2) == 8
