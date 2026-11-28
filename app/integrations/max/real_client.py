from typing import Any

import certifi
import httpx

from app.core.config import get_settings
from app.integrations.max.base import MaxClient


class RealMaxClient(MaxClient):
    """Skeleton for official MAX Bot API integration.

    Real endpoint paths/payloads must be verified against https://dev.max.ru/docs-api/
    before enabling in production.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.max_api_base_url.rstrip("/")
        self.token = settings.max_bot_token
        v = (settings.max_tls_verify or "true").strip().lower()
        if v in {"0", "false", "no", "off"}:
            self.verify: bool | str = False
        elif v in {"1", "true", "yes", "on", ""}:
            # Prefer system CA bundle so Docker image can ship Russian Trusted CA.
            import os
            for path in ("/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt"):
                if os.path.exists(path):
                    self.verify = path
                    break
            else:
                self.verify = certifi.where()
        else:
            self.verify = settings.max_tls_verify.strip()

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise RuntimeError("MAX_BOT_TOKEN is not configured")
        return {"Authorization": self.token}

    async def send_message(self, chat_id: int | str, text: str, **kwargs: Any) -> dict[str, Any]:
        params = dict(kwargs.pop("params", None) or {})
        # MAX API expects user_id or chat_id as query param; prefer explicit params.
        if "user_id" not in params and "chat_id" not in params:
            # Fallback: treat chat_id arg as user_id for direct messages.
            params["user_id"] = str(chat_id)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0, verify=self.verify) as client:
            response = await client.post(
                "/messages",
                headers=self._headers(),
                params=params,
                json={"text": text, **kwargs},
            )
            response.raise_for_status()
            return response.json()

    async def answer_callback(self, callback_id: str, **kwargs: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0, verify=self.verify) as client:
            response = await client.post(
                "/answers",
                headers=self._headers(),
                json={"callback_id": callback_id, **kwargs},
            )
            response.raise_for_status()
            return response.json()
