from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.webhook_max import router as webhook_max_router
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title=settings.app_name)
    app.include_router(health_router)
    app.include_router(webhook_max_router)
    return app


app = create_app()
