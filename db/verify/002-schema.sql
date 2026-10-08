SELECT version_num FROM alembic_version;
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('objects', 'mqtt_messages', 'mqtt_observations', 'ha_entities', 'object_links')
ORDER BY table_name;
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
