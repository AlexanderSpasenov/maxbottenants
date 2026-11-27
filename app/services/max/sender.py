from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.integrations.max.mock_client import MockMaxClient
from app.integrations.max.real_client import RealMaxClient

logger = logging.getLogger(__name__)


def get_max_client():
    settings = get_settings()
    if settings.max_bot_token:
        return RealMaxClient()
    return MockMaxClient()


async def send_text(chat_id: int | str, text: str, **kwargs: Any) -> dict[str, Any]:
    client = get_max_client()
    logger.info("Sending MAX message to chat_id=%s", chat_id)
    # MAX Bot API requires user_id/chat_id query param for direct/dialog messages.
    # For current prototype we map dialog chat_id to user_id when they match.
    send_kwargs = dict(kwargs)
    target_user_id = send_kwargs.pop("user_id", None) or send_kwargs.pop("max_user_id", None)
    target_chat_id = send_kwargs.pop("chat_id", None)
    # Heuristic: if only chat_id known and looks like dialog recipient id, also try user_id.
    if target_user_id is None and target_chat_id is None:
        try:
            cid = int(chat_id)
            target_user_id = cid
        except Exception:
            pass
    params = {}
    if target_user_id is not None:
        params["user_id"] = str(target_user_id)
    if target_chat_id is not None:
        params["chat_id"] = str(target_chat_id)
    if params:
        send_kwargs["params"] = {**params, **(send_kwargs.get("params") or {})}
    return await client.send_message(chat_id=chat_id, text=text, **send_kwargs)
