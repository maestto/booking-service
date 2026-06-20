"""Тест JSON-форматтера логов."""

import json
import logging

from app.core.logging import JsonLogFormatter


def test_json_log_formatter_includes_extra_fields() -> None:
    """JSON-форматтер кладёт в лог extra-поля вроде booking_id и status."""
    record = logging.LogRecord(
        name="app.worker.tasks",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Booking confirmed",
        args=(),
        exc_info=None,
    )
    record.booking_id = 1
    record.status = "confirmed"

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["level"] == "info"
    assert payload["logger"] == "app.worker.tasks"
    assert payload["message"] == "Booking confirmed"
    assert payload["booking_id"] == 1
    assert payload["status"] == "confirmed"
    assert "timestamp" in payload
