"""Persist globally exclusive source deletion and per-source progress."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_deletion_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("active_slot", sa.String(16), nullable=True, unique=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime().with_variant(mysql.DATETIME(fsp=6), "mysql"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
    )
    op.create_index("ix_source_deletion_jobs_created_at", "source_deletion_jobs", ["created_at"])
    op.create_table(
        "source_deletion_items",
        sa.Column("job_id", sa.String(64), sa.ForeignKey("source_deletion_jobs.id"), primary_key=True),
        sa.Column("source_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
    )
    op.create_index("ix_source_deletion_item_source", "source_deletion_items", ["source_id", "status"])


def downgrade():
    op.drop_table("source_deletion_items")
    op.drop_table("source_deletion_jobs")
