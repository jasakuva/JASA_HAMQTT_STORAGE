"""add local application authentication"""
from alembic import op
import sqlalchemy as sa


revision = "0007_application_authentication"
down_revision = "0006_graph_export_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "application_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=150), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_application_users_username", "application_users", ["username"])


def downgrade():
    op.drop_index("ix_application_users_username", table_name="application_users")
    op.drop_table("application_users")