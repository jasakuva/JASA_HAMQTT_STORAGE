"""deduplicate Home Assistant history observations"""
from alembic import op

revision = "0002_deduplicate_ha_history"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.exec_driver_sql("""
        DELETE FROM ha_state_history older
        USING ha_state_history newer
        WHERE older.ha_entity_id = newer.ha_entity_id
          AND older.observed_at = newer.observed_at
          AND older.id > newer.id
    """)
    op.create_unique_constraint(
        "uq_ha_state_history_entity_observed",
        "ha_state_history",
        ["ha_entity_id", "observed_at"],
    )


def downgrade():
    op.drop_constraint(
        "uq_ha_state_history_entity_observed",
        "ha_state_history",
        type_="unique",
    )