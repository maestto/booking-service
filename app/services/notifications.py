import logging

from app.models import Booking


logger = logging.getLogger(__name__)


def send_mock_notification(booking: Booking) -> None:
    """Мок отправки уведомления, пишет событие в лог."""
    logger.info(
        "Mock notification sent",
        extra={
            "booking_id": booking.id,
            "service_type": booking.service_type,
        },
    )
