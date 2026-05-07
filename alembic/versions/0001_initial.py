"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-07

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("plan", sa.Text(), nullable=False, server_default="free"),
        sa.Column("stripe_customer_id", sa.Text(), nullable=True),
        sa.Column("stripe_subscription_id", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("rules_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("action_thresholds", sa.JSON(), nullable=False),
        sa.Column("mute_duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("first_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "group_members",
        sa.Column("group_id", sa.BigInteger(), sa.ForeignKey("groups.id"), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.Text(), nullable=False, server_default="member"),
        sa.Column("warn_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.BigInteger(), sa.ForeignKey("groups.id"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("verdict_category", sa.String(length=32), nullable=False, server_default="ok"),
        sa.Column("verdict_severity", sa.String(length=16), nullable=False, server_default="none"),
        sa.Column("verdict_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("verdict_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("action_taken", sa.String(length=32), nullable=False, server_default="noop"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_group_created", "audit_log", ["group_id", "created_at"])
    op.create_table(
        "stripe_events",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("stripe_events")
    op.drop_index("ix_audit_log_group_created", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("group_members")
    op.drop_table("users")
    op.drop_table("groups")
