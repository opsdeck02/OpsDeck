from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "opsdeck",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.task_default_queue = "opsdeck.default"
celery_app.conf.beat_schedule = {
    "sync-microsoft-sources-every-15-minutes": {
        "task": "opsdeck.microsoft.sync_all",
        "schedule": 15 * 60,
    },
    "refresh-microsoft-tokens-every-20-minutes": {
        "task": "opsdeck.microsoft.refresh_tokens",
        "schedule": 20 * 60,
    },
}

import app.workers.tasks.microsoft_sync  # noqa: E402,F401
import app.workers.tasks.token_refresh  # noqa: E402,F401


@celery_app.task(name="opsdeck.tasks.ping")
def ping() -> str:
    return "pong"
