import logging
import time

from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info(
        "Event worker skeleton started; polling interval=%s",
        settings.worker_poll_interval_seconds,
    )
    while True:
        # Increment 3+: poll webhook_events/outbox tables.
        time.sleep(settings.worker_poll_interval_seconds)


if __name__ == "__main__":
    run()