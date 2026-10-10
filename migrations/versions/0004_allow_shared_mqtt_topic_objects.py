"""allow one shared MQTT topic object across broker connections"""
from alembic import op


revision = "0004_shared_mqtt_topic_objects"
down_revision = "0003_application_logs"
branch_labels = None
depends_on = None


def upgrade():
    # One shared object may represent the same topic on multiple brokers.
    op.drop_constraint("mqtt_topics_object_id_key", "mqtt_topics", type_="unique")


def downgrade():
    op.create_unique_constraint("mqtt_topics_object_id_key", "mqtt_topics", ["object_id"])