import random


class ExternalBookingServiceError(Exception):
    """Ошибка mock внешнего сервиса бронирования."""


def confirm_booking(booking_id: int) -> None:
    """Мок внешнего сервиса, с шансом около 15% выбрасывает ошибку."""
    if random.random() < 0.15:
        raise ExternalBookingServiceError(
            f"External booking service failed for booking {booking_id}"
        )
