-- PostgreSQL initialization for HA MQTT Store.
-- This file is executed once by the official PostgreSQL image when the
-- database volume is created for the first time.

CREATE EXTENSION IF NOT EXISTS vector;

COMMENT ON EXTENSION vector IS 'Vector similarity search for HA MQTT Store';
