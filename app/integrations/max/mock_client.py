from typing import Any

from app.integrations.max.base import MaxClient


class MockMaxClient(MaxClient):
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []
        self.answered_callbacks: list[dict[str, Any]] = []

    async def send_message(self, chat_id: int | str, text: str, **kwargs: Any) -> dict[str, Any]:
        payload = {"chat_id": chat_id, "text": text, **kwargs}
        self.sent_messages.append(payload)
        return {"ok": True, "mock": True, "payload": payload}

    async def answer_callback(self, callback_id: str, **kwargs: Any) -> dict[str, Any]:
        payload = {"callback_id": callback_id, **kwargs}
        self.answered_callbacks.append(payload)
        return {"ok": True, "mock": True, "payload": payload}
