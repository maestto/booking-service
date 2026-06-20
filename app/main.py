from fastapi import FastAPI

from app.api.bookings import router as bookings_router
from app.core.logging import configure_logging
from app.core.config import settings


configure_logging()

app = FastAPI(title=settings.app_name)
app.include_router(bookings_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
