from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.rate_limit import enforce_booking_rate_limit
from app.models import Booking, BookingStatus
from app.schemas.booking import BookingCreate, BookingRead
from app.worker.tasks import process_booking


router = APIRouter(prefix="/bookings", tags=["bookings"])


def enqueue_booking_processing(booking_id: int) -> None:
    """Ставит задачу обработки брони в очередь."""
    process_booking.delay(booking_id)


def get_booking_or_404(booking_id: int, db: Session) -> Booking:
    """Находит бронь по id или бросает 404."""
    booking = db.get(Booking, booking_id)

    if booking is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found",
        )

    return booking


@router.post(
    "",
    response_model=BookingRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_booking_rate_limit)],
    summary="Создать бронь",
    responses={429: {"description": "Превышен лимит запросов"}},
)
def create_booking(payload: BookingCreate, db: Session = Depends(get_db)) -> Booking:
    booking = Booking(
        name=payload.name,
        datetime=payload.datetime,
        service_type=payload.service_type,
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)

    enqueue_booking_processing(booking.id)

    return booking


@router.get("", response_model=List[BookingRead], summary="Список броней")
def list_bookings(
    booking_status: Optional[BookingStatus] = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Booking]:
    query = select(Booking).order_by(Booking.id).offset(offset).limit(limit)

    if booking_status is not None:
        query = query.where(Booking.status == booking_status)

    return list(db.scalars(query).all())


@router.get(
    "/{booking_id}",
    response_model=BookingRead,
    summary="Получить бронь",
    responses={404: {"description": "Бронь не найдена"}},
)
def get_booking(booking_id: int, db: Session = Depends(get_db)) -> Booking:
    return get_booking_or_404(booking_id, db)


@router.delete(
    "/{booking_id}",
    response_model=BookingRead,
    summary="Отменить бронь",
    responses={
        404: {"description": "Бронь не найдена"},
        400: {"description": "Отменить можно только бронь в статусе pending"},
    },
)
def cancel_booking(booking_id: int, db: Session = Depends(get_db)) -> Booking:
    booking = get_booking_or_404(booking_id, db)

    if booking.status != BookingStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending bookings can be cancelled",
        )

    booking.status = BookingStatus.CANCELLED
    db.commit()
    db.refresh(booking)

    return booking
