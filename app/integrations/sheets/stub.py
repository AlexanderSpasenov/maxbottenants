from typing import Any

from app.integrations.sheets.base import CatalogSource


class StubSheetsCatalogSource(CatalogSource):
    async def fetch_tenant_catalog(self, tenant_id: str) -> dict[str, Any]:
        return {"tenant_id": tenant_id, "source": "stub", "services": [], "masters": []}
