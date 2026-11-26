from typing import Any, Protocol


class MaxClient(Protocol):
    async def send_message(self, chat_id: int | str, text: str, **kwargs: Any) -> dict[str, Any]:
        """Send a text message to MAX chat."""

    async def answer_callback(self, callback_id: str, **kwargs: Any) -> dict[str, Any]:
        """Acknowledge callback query/button press."""
