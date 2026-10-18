-- PostgreSQL initialization for HA MQTT Store.
-- This file is executed once when the PostgreSQL data volume is initialized.

CREATE EXTENSION IF NOT EXISTS vector;

COMMENT ON EXTENSION vector IS 'Vector similarity search for HA MQTT Store';