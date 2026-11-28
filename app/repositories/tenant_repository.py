from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tenant import Tenant


class TenantRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_active(self) -> list[Tenant]:
        stmt = select(Tenant).where(Tenant.status == "active").order_by(Tenant.display_name)
        return list(self.db.scalars(stmt).all())

    def get_by_slug(self, slug: str) -> Tenant | None:
        stmt = select(Tenant).where(Tenant.slug == slug)
        return self.db.scalar(stmt)

    def get_by_id(self, tenant_id) -> Tenant | None:
        return self.db.get(Tenant, tenant_id)
