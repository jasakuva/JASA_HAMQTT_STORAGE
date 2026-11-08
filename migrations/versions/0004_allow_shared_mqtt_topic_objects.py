"""allow one shared MQTT topic object across broker connections"""
from alembic import op


revision = "0004_shared_mqtt_topic_objects"
down_revision = "0003_application_logs"
branch_labels = None
depends_on = None


def upgrade():
    # One shared object may represent the same topic on multiple brokers.
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
              AND t.relname = 'mqtt_topics'
              AND c.contype = 'u'
              AND array_length(c.conkey, 1) = 1
              AND a.attname = 'object_id'
            LIMIT 1;

            IF constraint_name IS NOT NULL THEN
                EXECUTE format('ALTER TABLE mqtt_topics DROP CONSTRAINT %%I', constraint_name);
            ELSE
                SELECT i.relname
                INTO index_name
                FROM pg_index x
                JOIN pg_class t ON t.oid = x.indrelid
                JOIN pg_class i ON i.oid = x.indexrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = x.indkey[0]
                WHERE n.nspname = current_schema()
                  AND t.relname = 'mqtt_topics'
                  AND x.indisunique
                  AND x.indnkeyatts = 1
                  AND a.attname = 'object_id'
                LIMIT 1;

                IF index_name IS NOT NULL THEN
                    EXECUTE format('DROP INDEX %%I', index_name);
                END IF;
            END IF;
        END $$;
        """
    )


def downgrade():
    op.create_unique_constraint("mqtt_topics_object_id_key", "mqtt_topics", ["object_id"])