"""outbox hardening

Revision ID: 0005_outbox_hardening
Revises: 0004_webhook_processing_claim
Create Date: 2026-11-27 00:00:03.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_outbox_hardening"
down_revision: str | Sequence[str] | None = "0004_webhook_processing_claim"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("outbox_messages", sa.Column("dedupe_key", sa.String(length=255), nullable=True))
    op.add_column(
        "outbox_messages",
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_outbox_messages_dedupe_key", "outbox_messages", ["dedupe_key"])
    op.create_index("ix_outbox_messages_next_attempt_at", "outbox_messages", ["next_attempt_at"])
    op.create_unique_constraint(
        "uq_outbox_tenant_dedupe_key", "outbox_messages", ["tenant_id", "dedupe_key"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_outbox_tenant_dedupe_key", "outbox_messages", type_="unique")
    op.drop_index("ix_outbox_messages_next_attempt_at", table_name="outbox_messages")
    op.drop_index("ix_outbox_messages_dedupe_key", table_name="outbox_messages")
    op.drop_column("outbox_messages", "next_attempt_at")
    op.drop_column("outbox_messages", "dedupe_key")