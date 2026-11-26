"""webhook processing claim

Revision ID: 0004_webhook_processing_claim
Revises: 0003_tenant_fk_hardening
Create Date: 2026-11-26 00:00:02.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_webhook_processing_claim"
down_revision: str | Sequence[str] | None = "0003_tenant_fk_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "webhook_events",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_webhook_events_status_received_at",
        "webhook_events",
        ["status", "received_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_events_status_received_at", table_name="webhook_events")
    op.drop_column("webhook_events", "processing_started_at")
