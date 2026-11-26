"""tenant fk hardening

Revision ID: 0003_tenant_fk_hardening
Revises: 0002_core_multitenant_schema
Create Date: 2026-11-26 00:00:01.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_tenant_fk_hardening"
down_revision: str | Sequence[str] | None = "0002_core_multitenant_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_bookings_tenant_service",
        "bookings",
        "services",
        ["tenant_id", "service_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_bookings_tenant_master",
        "bookings",
        "masters",
        ["tenant_id", "master_id"],
        ["tenant_id", "id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_master_working_hours_tenant_master",
        "master_working_hours",
        "masters",
        ["tenant_id", "master_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_schedule_exceptions_tenant_master",
        "schedule_exceptions",
        "masters",
        ["tenant_id", "master_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_schedule_exceptions_tenant_master", "schedule_exceptions", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_master_working_hours_tenant_master", "master_working_hours", type_="foreignkey"
    )
    op.drop_constraint("fk_bookings_tenant_master", "bookings", type_="foreignkey")
    op.drop_constraint("fk_bookings_tenant_service", "bookings", type_="foreignkey")
