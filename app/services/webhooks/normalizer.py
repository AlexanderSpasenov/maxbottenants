from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_max_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize MAX webhook payload into a stable internal shape.

    This is a defensive adapter: it accepts current fixture-like payloads and
    plausible callback/button variants without assuming the final MAX contract.
    Unknown/unconfirmed fields are preserved under `raw`.
    """

    raw = payload if isinstance(payload, dict) else {"_raw": payload}
    event_type = str(raw.get("update_type") or raw.get("type") or "unknown")
    ts = raw.get("timestamp")

    msg = _as_dict(raw.get("message"))
    body = _as_dict(msg.get("body"))
    sender = _as_dict(msg.get("sender") or msg.get("from") or msg.get("user"))
    recipient = _as_dict(msg.get("recipient"))
    callback = _as_dict(raw.get("callback") or raw.get("callback_query"))

    chat_id = (
        msg.get("chat_id")
        or recipient.get("chat_id")
        or callback.get("chat_id")
        or _as_dict(callback.get("message")).get("chat_id")
        or raw.get("chat_id")
    )
    # For callbacks prefer the clicking user; message.sender is the bot.
    user_id = (
        callback.get("user_id")
        or _as_dict(callback.get("user")).get("user_id")
        or _as_dict(callback.get("user")).get("id")
        or sender.get("user_id")
        or sender.get("id")
        or raw.get("user_id")
    )
    mid = msg.get("mid") or body.get("mid") or msg.get("id") or raw.get("message_id")
    callback_id = callback.get("callback_id") or callback.get("id")
    # Contract-agnostic: payload/data/button value may carry command/start token.
    callback_payload = (
        callback.get("payload")
        or callback.get("data")
        or callback.get("value")
        or body.get("payload")
    )
    text = body.get("text") or raw.get("text")
    # For callbacks, payload/data carries the button action; body.text is the
    # message text and must not override callback payload.
    if callback_payload is not None and str(event_type) == "message_callback":
        text = str(callback_payload)
    elif not text and callback_payload is not None:
        text = str(callback_payload)

    normalized = {
        "event_type": event_type,
        "timestamp": ts,
        "chat_id": int(chat_id) if str(chat_id).isdigit() else chat_id,
        "user_id": int(user_id) if str(user_id).isdigit() else user_id,
        "message_id": str(mid) if mid is not None else None,
        "callback_id": str(callback_id) if callback_id is not None else None,
        "text": str(text).strip() if text is not None else "",
        "callback_payload": callback_payload,
        "sender_name": sender.get("name"),
        "raw": raw,
    }
    return normalized
