"""add updater jobs and safe points"""
from alembic import op
import sqlalchemy as sa

revision = "0009_update_jobs_and_safe_points"
down_revision = "0008_backup_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "update_safe_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("application_version", sa.String(length=80), nullable=False),
        sa.Column("image_tag", sa.String(length=255), nullable=False),
        sa.Column("image_digests", sa.JSON()),
        sa.Column("backup_run_id", sa.Integer()),
        sa.Column("env_file_hash", sa.String(length=64)),
        sa.Column("compose_file_hash", sa.String(length=64)),
        sa.Column("engine", sa.String(length=20), nullable=False, server_default="podman"),
        sa.Column("project_name", sa.String(length=100), nullable=False, server_default="hamqtt-store"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ready"),
        sa.Column("invalid_reason", sa.Text()),
    )
    op.create_index("ix_update_safe_points_created_at", "update_safe_points", ["created_at"])
    op.create_index("ix_update_safe_points_backup_run_id", "update_safe_points", ["backup_run_id"])
    op.create_index("ix_update_safe_points_status", "update_safe_points", ["status"])
    op.create_table(
        "update_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("requested_by_user_id", sa.Integer()),
        sa.Column("operation", sa.String(length=20), nullable=False, server_default="update"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("current_step", sa.String(length=80)),
        sa.Column("current_version", sa.String(length=80)),
        sa.Column("target_version", sa.String(length=80), nullable=False),
        sa.Column("previous_version", sa.String(length=80)),
        sa.Column("engine", sa.String(length=20), nullable=False, server_default="podman"),
        sa.Column("safe_point_id", sa.Integer()),
        sa.Column("error_code", sa.String(length=80)),
        sa.Column("error_summary", sa.Text()),
        sa.Column("rollback_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requires_manual_action", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_update_jobs_created_at", "update_jobs", ["created_at"])
    op.create_index("ix_update_jobs_operation", "update_jobs", ["operation"])
    op.create_index("ix_update_jobs_status", "update_jobs", ["status"])
    op.create_index("ix_update_jobs_safe_point_id", "update_jobs", ["safe_point_id"])


def downgrade():
    op.drop_index("ix_update_jobs_safe_point_id", table_name="update_jobs")
    op.drop_index("ix_update_jobs_status", table_name="update_jobs")
    op.drop_index("ix_update_jobs_operation", table_name="update_jobs")
    op.drop_index("ix_update_jobs_created_at", table_name="update_jobs")
    op.drop_table("update_jobs")
    op.drop_index("ix_update_safe_points_status", table_name="update_safe_points")
    op.drop_index("ix_update_safe_points_backup_run_id", table_name="update_safe_points")
    op.drop_index("ix_update_safe_points_created_at", table_name="update_safe_points")
    op.drop_table("update_safe_points")