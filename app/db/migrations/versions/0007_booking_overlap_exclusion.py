"""booking overlap exclusion

Revision ID: 0007_booking_overlap_exclusion
Revises: 0006_online_booking_hardening
Create Date: 2026-11-27 00:00:02
"""

from alembic import op

revision = "0007_booking_overlap_exclusion"
down_revision = "0006_online_booking_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        """
        ALTER TABLE bookings
        ADD CONSTRAINT ex_bookings_master_slot_no_overlap
        EXCLUDE USING gist (
            tenant_id WITH =,
            master_id WITH =,
            tstzrange(slot_start, slot_end, '[)') WITH &&
        )
        WHERE (
            slot_start IS NOT NULL
            AND slot_end IS NOT NULL
            AND status IN ('awaiting_salon', 'pending_confirmation', 'confirmed')
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ex_bookings_master_slot_no_overlap"
    )
