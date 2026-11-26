from fastapi import APIRouter, Depends, Request

from app.core.security import verify_max_webhook_secret

router = APIRouter(tags=["max-webhook"])


@router.post("/webhook/max")
async def max_webhook(
    request: Request,
    _: None = Depends(verify_max_webhook_secret),
) -> dict[str, bool]:
    # Increment 1 skeleton: accept payload and acknowledge.
    # Increment 3 will add persistence, deduplication, and worker dispatch.
    _ = await request.json()
    return {"ok": True}