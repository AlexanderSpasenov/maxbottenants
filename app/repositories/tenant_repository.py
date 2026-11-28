import re
import uuid

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

    @staticmethod
    def slugify(name: str) -> str:
        translit = {
            "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z","и":"i","й":"y",
            "к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f",
            "х":"h","ц":"ts","ч":"ch","ш":"sh","щ":"sch","ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
        }
        s = (name or "").strip().lower()
        s = "".join(translit.get(ch, ch) for ch in s)
        s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
        s = re.sub(r"-{2,}", "-", s)
        return s[:80] or "salon"

    def create_with_unique_slug(self, *, display_name: str, timezone: str = "Europe/Moscow", booking_mode: str = "request_only") -> Tenant:
        base = self.slugify(display_name)
        slug = base
        i = 2
        while self.get_by_slug(slug) is not None:
            suffix = f"-{i}"
            slug = f"{base[: max(1, 80-len(suffix))]}{suffix}"
            i += 1
        tenant = Tenant(
            id=uuid.uuid4(),
            slug=slug,
            display_name=display_name.strip(),
            status="active",
            timezone=timezone,
            booking_mode=booking_mode,
        )
        self.db.add(tenant)
        self.db.flush()
        return tenant
