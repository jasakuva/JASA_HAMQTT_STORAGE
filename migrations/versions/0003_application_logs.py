"""add persistent application diagnostic logs"""
from alembic import op
import sqlalchemy as sa

revision = "0003_application_logs"
down_revision = "0002_deduplicate_ha_history"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "application_logs" in inspector.get_table_names():
        return
    op.create_table(
        "application_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=150), nullable=False),
        sa.Column("event", sa.String(length=100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_application_logs_created_at", "application_logs", ["created_at"])
    op.create_index("ix_application_logs_level", "application_logs", ["level"])
    op.create_index("ix_application_logs_source", "application_logs", ["source"])
    op.create_index("ix_application_logs_event", "application_logs", ["event"])
    op.create_index("ix_application_logs_connection_id", "application_logs", ["connection_id"])


def downgrade():
    op.drop_index("ix_application_logs_connection_id", table_name="application_logs")
    op.drop_index("ix_application_logs_event", table_name="application_logs")
    op.drop_index("ix_application_logs_source", table_name="application_logs")
    op.drop_index("ix_application_logs_level", table_name="application_logs")
    op.drop_index("ix_application_logs_created_at", table_name="application_logs")
    op.drop_table("application_logs")