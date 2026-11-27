"""online booking hardening

Revision ID: 0006_online_booking_hardening
Revises: 0005_outbox_hardening
Create Date: 2026-11-27 00:00:01
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_online_booking_hardening"
down_revision = "0005_outbox_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "online_booking_auto_confirm",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "online_booking_hold_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("15"),
        ),
    )
    op.create_index(
        "uq_bookings_active_slot_start",
        "bookings",
        ["tenant_id", "master_id", "slot_start"],
        unique=True,
        postgresql_where=sa.text(
            "slot_start IS NOT NULL AND status IN "
            "('awaiting_salon','pending_confirmation','confirmed')"
        ),
    )
    op.create_index(
        "ix_bookings_expires_at_status",
        "bookings",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_bookings_expires_at_status", table_name="bookings")
    op.drop_index("uq_bookings_active_slot_start", table_name="bookings")
    op.drop_column("tenants", "online_booking_hold_minutes")
    op.drop_column("tenants", "online_booking_auto_confirm")
