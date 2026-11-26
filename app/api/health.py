from fastapi import APIRouter, Depends
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    db.execute(text("SELECT 1"))

    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        redis_client.ping()
    finally:
        redis_client.close()

    return {"status": "ok"}