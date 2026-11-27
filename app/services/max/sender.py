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
    return await client.send_message(chat_id=chat_id, text=text, **kwargs)
