"""initial HA MQTT Store schema"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    from hamqtt_store.db import Base
    bind = op.get_bind()
    bind.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    # Only create tables that belonged to the initial revision.  Base.metadata
    # also contains models introduced by later migrations, and creating all of
    # them here makes those later migrations fail with DuplicateTable.
    initial_tables = {
        table_name: table
        for table_name, table in Base.metadata.tables.items()
        if table_name not in {"application_logs", "application_users", "backup_runs"}
    }
    Base.metadata.create_all(bind=bind, tables=list(initial_tables.values()))

def downgrade():
    from hamqtt_store.db import Base
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
