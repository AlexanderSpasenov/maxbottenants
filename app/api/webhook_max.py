import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.security import verify_max_webhook_secret
from app.db.session import get_db
from app.repositories.webhook_event_repository import WebhookEventRepository
from app.services.webhooks.idempotency import build_event_key, detect_event_type

logger = logging.getLogger(__name__)

router = APIRouter(tags=["max-webhook"])

SENSITIVE_KEYS = {
    "phone",
    "customer_phone",
    "customer_phone_encrypted",
    "token",
    "secret",
    "authorization",
    "access_token",
}


def _redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = _redact_payload(item)
        return redacted
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    return value


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

    payload = _redact_payload(payload)

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
