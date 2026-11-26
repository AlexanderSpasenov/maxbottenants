import hmac

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


def verify_max_webhook_secret(x_max_bot_api_secret: str | None = Header(default=None)) -> None:
    settings = get_settings()
    expected = settings.max_webhook_secret
    if not expected:
        # Local development before real MAX bot is provisioned.
        return
    if not x_max_bot_api_secret or not hmac.compare_digest(x_max_bot_api_secret, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )