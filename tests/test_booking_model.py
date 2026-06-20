"""Тесты модели Booking: статус по умолчанию и значения enum."""

import datetime as dt

from sqlalchemy.orm import sessionmaker

from app.models import Booking, BookingStatus


def test_booking_model_sets_pending_status_by_default(session_factory: sessionmaker) -> None:
    """Новая бронь по умолчанию создаётся в статусе pending."""
    with session_factory() as db:
        booking = Booking(
            name="Alex",
            datetime=dt.datetime(2026, 7, 1, 10, 30, tzinfo=dt.timezone.utc),
            service_type="consultation",
        )

        db.add(booking)
        db.commit()
        db.refresh(booking)

        assert booking.id is not None
        assert booking.status == BookingStatus.PENDING
        assert booking.name == "Alex"


def test_booking_status_values_match_api_contract() -> None:
    """Значения enum совпадают с тем, что отдаёт API."""
    assert [status.value for status in BookingStatus] == [
        "pending",
        "confirmed",
        "failed",
        "cancelled",
    ]
