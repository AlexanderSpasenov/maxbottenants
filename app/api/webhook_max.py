import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.security import verify_max_webhook_secret
from app.db.session import get_db
from app.repositories.webhook_event_repository import WebhookEventRepository
from app.services.webhooks.idempotency import build_event_key, detect_event_type

logger = logging.getLogger(__name__)

router = APIRouter(tags=["max-webhook"])


@router.post("/webhook/max")
async def max_webhook(
    request: Request,
    _: None = Depends(verify_max_webhook_secret),
    db: Session = Depends(get_db),
) -> dict[str, bool | str]:
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    if not isinstance(payload, dict):
        payload = {"_raw": payload}

    event_key = build_event_key(payload)
    event_type = detect_event_type(payload)
    repo = WebhookEventRepository(db)
    event, created = repo.create_received(
        event_key=event_key, event_type=event_type, payload=payload
    )
    db.commit()
    logger.info(
        "Webhook received key=%s type=%s created=%s id=%s",
        event_key,
        event_type,
        created,
        event.id,
    )
    return {"ok": True, "event_key": event_key, "duplicate": not created}
