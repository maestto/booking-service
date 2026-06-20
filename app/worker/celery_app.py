from celery import Celery

from app.core.config import settings
from app.core.logging import configure_logging


configure_logging()


celery_app = Celery(
    "booking_service",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.tasks"],
)
celery_app.conf.worker_hijack_root_logger = False

celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True
