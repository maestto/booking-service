import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from app.models import BookingStatus


class BookingCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    datetime: dt.datetime
    service_type: str = Field(min_length=1, max_length=100)


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    datetime: dt.datetime
    service_type: str
    status: BookingStatus
    created_at: dt.datetime
    updated_at: dt.datetime
