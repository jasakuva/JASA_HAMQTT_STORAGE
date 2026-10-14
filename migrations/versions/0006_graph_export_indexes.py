"""add indexes used by graph and export history queries"""
from alembic import op


revision = "0006_graph_export_indexes"
down_revision = "0005_shared_mqtt_field_objects"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_mqtt_observations_field_observed "
        "ON mqtt_observations (mqtt_payload_field_id, observed_at)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_ha_entities_object_id "
        "ON ha_entities (object_id)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_mqtt_payload_fields_object_id "
        "ON mqtt_payload_fields (object_id)"
    )


def downgrade():
    op.drop_index("ix_mqtt_payload_fields_object_id", table_name="mqtt_payload_fields")
    op.drop_index("ix_ha_entities_object_id", table_name="ha_entities")
    op.drop_index("ix_mqtt_observations_field_observed", table_name="mqtt_observations")