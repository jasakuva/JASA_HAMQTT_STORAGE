SELECT current_database() AS database_name, version();
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'vector';
