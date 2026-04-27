from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "steelops",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.task_default_queue = "steelops.default"


@celery_app.task(name="steelops.tasks.ping")
def ping() -> str:
    return "pong"

