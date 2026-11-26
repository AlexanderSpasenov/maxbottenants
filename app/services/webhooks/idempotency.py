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
    update_type = str(payload.get("update_type") or "unknown")
    msg = _extract_message(payload)
    callback = _extract_callback(payload)

    body = msg.get("body") if isinstance(msg.get("body"), dict) else {}
    sender = msg.get("sender") if isinstance(msg.get("sender"), dict) else {}
    recipient = msg.get("recipient") if isinstance(msg.get("recipient"), dict) else {}

    candidates = [
        payload.get("event_id"),
        payload.get("update_id"),
        payload.get("event_key"),
        msg.get("mid"),
        body.get("mid"),
        msg.get("id"),
        callback.get("callback_id"),
        callback.get("id"),
    ]
    for value in candidates:
        if value is not None and str(value).strip():
            return f"max:{update_type}:{value}"

    fingerprint = {
        "update_type": update_type,
        "timestamp": payload.get("timestamp"),
        "chat_id": msg.get("chat_id") or recipient.get("chat_id") or callback.get("chat_id"),
        "user_id": sender.get("user_id") or callback.get("user_id"),
        "text": body.get("text"),
        "payload": callback.get("payload"),
    }
    raw = json.dumps(fingerprint, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"max:{update_type}:hash:{digest}"


def detect_event_type(payload: dict[str, Any]) -> str:
    return str(payload.get("update_type") or "unknown")
