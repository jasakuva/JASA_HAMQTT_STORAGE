"""allow one shared MQTT field object across topic rows"""
from alembic import op


revision = "0005_shared_mqtt_field_objects"
down_revision = "0004_shared_mqtt_topic_objects"
branch_labels = None
depends_on = None


def upgrade():
    # One shared object may represent the same parsed field on multiple topic rows.
    # The initial schema is created from the current models, so a fresh
    # database may not have the historical unique constraint at all. Older
    # databases may also have a generated name or a standalone unique index.
    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        DO $$
        DECLARE
            constraint_name text;
            index_name text;
        BEGIN
            SELECT c.conname
            INTO constraint_name
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = c.conkey[1]
            WHERE n.nspname = current_schema()
              AND t.relname = 'mqtt_payload_fields'
              AND c.contype = 'u'
              AND array_length(c.conkey, 1) = 1
              AND a.attname = 'object_id'
            LIMIT 1;

            IF constraint_name IS NOT NULL THEN
                EXECUTE format('ALTER TABLE mqtt_payload_fields DROP CONSTRAINT %I', constraint_name);
            ELSE
                SELECT i.relname
                INTO index_name
                FROM pg_index x
                JOIN pg_class t ON t.oid = x.indrelid
                JOIN pg_class i ON i.oid = x.indexrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = x.indkey[0]
                WHERE n.nspname = current_schema()
                  AND t.relname = 'mqtt_payload_fields'
                  AND x.indisunique
                  AND x.indnkeyatts = 1
                  AND a.attname = 'object_id'
                LIMIT 1;

                IF index_name IS NOT NULL THEN
                    EXECUTE format('DROP INDEX %I', index_name);
                END IF;
            END IF;
        END $$;
        """
    )


def downgrade():
    op.create_unique_constraint("mqtt_payload_fields_object_id_key", "mqtt_payload_fields", ["object_id"])