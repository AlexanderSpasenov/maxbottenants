from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from app.integrations.sheets.base import CatalogSource


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


class CsvCatalogSource(CatalogSource):
    """Read-only catalog source for local fixtures/exports.

    Expected files in `base_dir` (all optional):
    - services.csv
    - masters.csv
    - service_masters.csv
    - master_working_hours.csv
    - schedule_exceptions.csv
    """

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)

    async def fetch_tenant_catalog(self, tenant_id: str) -> dict[str, Any]:
        return {
            "tenant_id": tenant_id,
            "source": "csv",
            "services": _read_csv(self.base_dir / "services.csv"),
            "masters": _read_csv(self.base_dir / "masters.csv"),
            "service_masters": _read_csv(self.base_dir / "service_masters.csv"),
            "master_working_hours": _read_csv(self.base_dir / "master_working_hours.csv"),
            "schedule_exceptions": _read_csv(self.base_dir / "schedule_exceptions.csv"),
        }
