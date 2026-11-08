"""add backup run history"""
from alembic import op
import sqlalchemy as sa


revision = "0008_backup_runs"
down_revision = "0007_application_authentication"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "backup_runs" not in inspector.get_table_names():
        op.create_table(
            "backup_runs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("backup_type", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
            sa.Column("label", sa.String(length=255)),
            sa.Column("size_bytes", sa.BigInteger()),
            sa.Column("error_message", sa.Text()),
            sa.Column("triggered_by", sa.String(length=30), nullable=False, server_default="schedule"),
        )
    index_names = {index["name"] for index in sa.inspect(bind).get_indexes("backup_runs")}
    for index_name, column_name in (
        ("ix_backup_runs_backup_type", "backup_type"),
        ("ix_backup_runs_status", "status"),
        ("ix_backup_runs_started_at", "started_at"),
    ):
        if index_name not in index_names:
            op.create_index(index_name, "backup_runs", [column_name])


def downgrade():
    op.drop_index("ix_backup_runs_started_at", table_name="backup_runs")
    op.drop_index("ix_backup_runs_status", table_name="backup_runs")
    op.drop_index("ix_backup_runs_backup_type", table_name="backup_runs")
    op.drop_table("backup_runs")