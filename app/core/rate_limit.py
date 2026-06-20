import math
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import HTTPException, Request, status

from app.core.config import settings


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__("Rate limit exceeded")


class InMemoryRateLimiter:
    """Лимитер запросов на скользящем окне, счётчики живут в памяти процесса."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: defaultdict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str, now: Optional[float] = None) -> None:
        """Регистрирует запрос и бросает RateLimitExceeded, если лимит превышен."""
        current_time = now if now is not None else time.monotonic()
        bucket = self._requests[key]
        window_start = current_time - self.window_seconds

        while bucket and bucket[0] <= window_start:
            bucket.popleft()

        if len(bucket) >= self.limit:
            retry_after = math.ceil(self.window_seconds - (current_time - bucket[0]))
            raise RateLimitExceeded(retry_after=max(1, retry_after))

        bucket.append(current_time)

    def reset(self) -> None:
        self._requests.clear()


bookings_rate_limiter = InMemoryRateLimiter(
    limit=settings.bookings_rate_limit_per_minute,
    window_seconds=60,
)


def get_client_key(request: Request) -> str:
    if request.client is None:
        return "unknown"

    return request.client.host


def enforce_booking_rate_limit(request: Request) -> None:
    """Зависимость FastAPI, при превышении лимита отдаёт 429."""
    try:
        bookings_rate_limiter.hit(get_client_key(request))
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many booking requests",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
