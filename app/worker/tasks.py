import logging
from typing import Optional

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Booking, BookingStatus
from app.services.external_booking import (
    ExternalBookingServiceError,
    confirm_booking,
)
from app.services.notifications import send_mock_notification
from app.worker.celery_app import celery_app


logger = logging.getLogger(__name__)


def get_retry_countdown(retries: int) -> int:
    """Задержка перед повтором, растёт по степени двойки."""
    return settings.celery_retry_backoff_seconds * (2**retries)


def process_booking_logic(booking_id: int) -> Optional[BookingStatus]:
    """Обрабатывает бронь, подтверждает только pending, остальные пропускает."""
    with SessionLocal() as db:
        booking = db.get(Booking, booking_id, with_for_update=True)

        if booking is None:
            logger.warning("Booking not found", extra={"booking_id": booking_id})
            return None

        if booking.status != BookingStatus.PENDING:
            logger.info(
                "Booking processing skipped",
                extra={
                    "booking_id": booking.id,
                    "status": booking.status.value,
                },
            )
            return booking.status

        try:
            confirm_booking(booking.id)
        except ExternalBookingServiceError:
            logger.warning(
                "Booking external confirmation failed",
                extra={
                    "booking_id": booking.id,
                },
            )
            raise
        else:
            booking.status = BookingStatus.CONFIRMED
            logger.info(
                "Booking confirmed",
                extra={
                    "booking_id": booking.id,
                    "status": booking.status.value,
                },
            )
            send_mock_notification(booking)

        db.commit()
        db.refresh(booking)

        return booking.status


def mark_booking_failed(booking_id: int) -> Optional[BookingStatus]:
    """Переводит бронь в failed, когда попытки кончились."""
    with SessionLocal() as db:
        booking = db.get(Booking, booking_id, with_for_update=True)

        if booking is None:
            logger.warning("Booking not found", extra={"booking_id": booking_id})
            return None

        if booking.status != BookingStatus.PENDING:
            logger.info(
                "Booking final failure skipped",
                extra={
                    "booking_id": booking.id,
                    "status": booking.status.value,
                },
            )
            return booking.status

        booking.status = BookingStatus.FAILED
        logger.warning(
            "Booking processing failed after retries",
            extra={
                "booking_id": booking.id,
                "status": booking.status.value,
            },
        )

        db.commit()
        db.refresh(booking)

        return booking.status


@celery_app.task(
    bind=True,
    name="process_booking",
    max_retries=settings.celery_task_max_retries,
)
def process_booking(self, booking_id: int) -> Optional[str]:
    """Celery-задача, запускает обработку и при ошибке планирует повтор или failed."""
    try:
        status = process_booking_logic(booking_id)
    except ExternalBookingServiceError as exc:
        if self.request.retries >= settings.celery_task_max_retries:
            status = mark_booking_failed(booking_id)
        else:
            countdown = get_retry_countdown(self.request.retries)
            logger.warning(
                "Booking processing retry scheduled",
                extra={
                    "booking_id": booking_id,
                    "retry": self.request.retries + 1,
                    "countdown": countdown,
                },
            )
            raise self.retry(exc=exc, countdown=countdown)

    if status is None:
        return None

    return status.value
