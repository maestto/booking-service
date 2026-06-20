import os
from dataclasses import dataclass
from functools import lru_cache


def _get_int_env(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    database_url: str
    celery_broker_url: str
    celery_result_backend: str
    celery_task_max_retries: int
    celery_retry_backoff_seconds: int
    bookings_rate_limit_per_minute: int


@lru_cache
def get_settings() -> Settings:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    return Settings(
        app_name=os.getenv("APP_NAME", "Booking Service"),
        app_env=os.getenv("APP_ENV", "development"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./booking.db"),
        celery_broker_url=os.getenv("CELERY_BROKER_URL", redis_url),
        celery_result_backend=os.getenv("CELERY_RESULT_BACKEND", redis_url),
        celery_task_max_retries=_get_int_env("CELERY_TASK_MAX_RETRIES", 3),
        celery_retry_backoff_seconds=_get_int_env("CELERY_RETRY_BACKOFF_SECONDS", 2),
        bookings_rate_limit_per_minute=_get_int_env(
            "BOOKINGS_RATE_LIMIT_PER_MINUTE",
            60,
        ),
    )


settings = get_settings()
