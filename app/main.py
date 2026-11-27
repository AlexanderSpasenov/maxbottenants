import logging

from fastapi import FastAPI

from app.api.admin_sync import router as admin_sync_router
from app.api.health import router as health_router
from app.api.webhook_max import router as webhook_max_router
from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    for warning in settings.validate_runtime():
        logger.warning("Config warning: %s", warning)

    app = FastAPI(title=settings.app_name)
    app.include_router(health_router)
    app.include_router(webhook_max_router)
    app.include_router(admin_sync_router)
    return app


app = create_app()
