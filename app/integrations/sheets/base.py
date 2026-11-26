from typing import Any, Protocol


class CatalogSource(Protocol):
    async def fetch_tenant_catalog(self, tenant_id: str) -> dict[str, Any]:
        """Fetch normalized catalog/settings data for tenant."""
