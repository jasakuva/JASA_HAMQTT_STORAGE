"""allow one shared MQTT field object across topic rows"""
from alembic import op


revision = "0005_shared_mqtt_field_objects"
down_revision = "0004_shared_mqtt_topic_objects"
branch_labels = None
depends_on = None


def upgrade():
    # One shared object may represent the same parsed field on multiple topic rows.
    op.drop_constraint("mqtt_payload_fields_object_id_key", "mqtt_payload_fields", type_="unique")


def downgrade():
    op.create_unique_constraint("mqtt_payload_fields_object_id_key", "mqtt_payload_fields", ["object_id"])