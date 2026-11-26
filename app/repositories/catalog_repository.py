import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import Master, Service, ServiceMaster


class CatalogRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_active_services(self, tenant_id: uuid.UUID) -> list[Service]:
        stmt = (
            select(Service)
            .where(Service.tenant_id == tenant_id, Service.is_active.is_(True))
            .order_by(Service.name)
        )
        return list(self.db.scalars(stmt).all())

    def get_service(self, tenant_id: uuid.UUID, service_id: uuid.UUID) -> Service | None:
        stmt = select(Service).where(Service.tenant_id == tenant_id, Service.id == service_id)
        return self.db.scalar(stmt)

    def list_active_masters(self, tenant_id: uuid.UUID) -> list[Master]:
        stmt = (
            select(Master)
            .where(Master.tenant_id == tenant_id, Master.is_active.is_(True))
            .order_by(Master.display_name)
        )
        return list(self.db.scalars(stmt).all())

    def list_service_masters(self, tenant_id: uuid.UUID, service_id: uuid.UUID) -> list[Master]:
        stmt = (
            select(Master)
            .join(ServiceMaster, ServiceMaster.master_id == Master.id)
            .where(
                ServiceMaster.tenant_id == tenant_id,
                ServiceMaster.service_id == service_id,
                ServiceMaster.is_active.is_(True),
                Master.tenant_id == tenant_id,
                Master.is_active.is_(True),
            )
            .order_by(Master.display_name)
        )
        return list(self.db.scalars(stmt).all())
