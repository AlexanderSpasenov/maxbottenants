"""Repository layer. All tenant-data queries must require tenant_id."""

from app.repositories.booking_repository import BookingRepository
from app.repositories.catalog_repository import CatalogRepository
from app.repositories.customer_profile_repository import CustomerProfileRepository
from app.repositories.dialog_session_repository import DialogSessionRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.tenant_link_repository import TenantLinkRepository
from app.repositories.tenant_member_repository import TenantMemberRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.webhook_event_repository import WebhookEventRepository

__all__ = [
    "BookingRepository",
    "CatalogRepository",
    "CustomerProfileRepository",
    "DialogSessionRepository",
    "OutboxRepository",
    "TenantLinkRepository",
    "TenantMemberRepository",
    "TenantRepository",
    "WebhookEventRepository",
]
