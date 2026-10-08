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
    Base.metadata.create_all(bind=bind)

def downgrade():
    from hamqtt_store.db import Base
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
