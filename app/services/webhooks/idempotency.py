from __future__ import annotations

import hashlib
import json
from typing import Any


def _extract_message(payload: dict[str, Any]) -> dict[str, Any]:
    msg = payload.get("message")
    return msg if isinstance(msg, dict) else {}


def _extract_callback(payload: dict[str, Any]) -> dict[str, Any]:
    cb = payload.get("callback")
    return cb if isinstance(cb, dict) else {}


def build_event_key(payload: dict[str, Any]) -> str:
    from app.services.webhooks.normalizer import normalize_max_event

    n = normalize_max_event(payload)
    update_type = str(n.get("event_type") or "unknown")

    candidates = [
        payload.get("event_id"),
        payload.get("update_id"),
        payload.get("event_key"),
        n.get("message_id"),
        n.get("callback_id"),
    ]
    for value in candidates:
        if value is not None and str(value).strip():
            return f"max:{update_type}:{value}"

    fingerprint = {
        "update_type": update_type,
        "timestamp": n.get("timestamp"),
        "chat_id": n.get("chat_id"),
        "user_id": n.get("user_id"),
        "text": n.get("text"),
        "payload": n.get("callback_payload"),
    }
    raw = json.dumps(fingerprint, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"max:{update_type}:hash:{digest}"


def detect_event_type(payload: dict[str, Any]) -> str:
    return str(payload.get("update_type") or "unknown")
