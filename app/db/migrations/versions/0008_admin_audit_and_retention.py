"""admin audit log

Revision ID: 0008_admin_audit_and_retention
Revises: 0007_booking_overlap_exclusion
Create Date: 2026-11-27 00:00:03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_admin_audit_and_retention"
down_revision = "0007_booking_overlap_exclusion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tenant_slug", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_admin_audit_log_action"), "admin_audit_log", ["action"], unique=False)
    op.create_index(
        op.f("ix_admin_audit_log_created_at"),
        "admin_audit_log",
        ["created_at"],
        unique=False,
    )
    op.create_index(op.f("ix_admin_audit_log_status"), "admin_audit_log", ["status"], unique=False)
    op.create_index(op.f("ix_admin_audit_log_tenant_id"), "admin_audit_log", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_admin_audit_log_tenant_slug"), "admin_audit_log", ["tenant_slug"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_audit_log_tenant_slug"), table_name="admin_audit_log")
    op.drop_index(op.f("ix_admin_audit_log_tenant_id"), table_name="admin_audit_log")
    op.drop_index(op.f("ix_admin_audit_log_status"), table_name="admin_audit_log")
    op.drop_index(op.f("ix_admin_audit_log_created_at"), table_name="admin_audit_log")
    op.drop_index(op.f("ix_admin_audit_log_action"), table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
