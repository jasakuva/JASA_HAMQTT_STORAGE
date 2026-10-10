# HA MQTT Store 0.2.1

Release date: 2026-10-10

## Highlights

Version 0.2.1 is a maintenance release focused on MQTT reliability, clearer Settings behavior, operational diagnostics, and safer upgrades.

## Fixed

- Fixed MQTT Settings selecting an older disabled connection instead of the active enabled connection.
- Fixed MQTT topic storage when the same shared topic object is used by multiple broker-specific topic rows.
- Fixed MQTT payload-field storage when the same shared field object is used by multiple topic rows.
- MQTT messages now continue to be stored correctly after the database constraint fixes are applied.
- MQTT worker diagnostics now include connection context and actionable failure details without logging credentials or payloads.

## Improved

- Added persistent application logs with readable details on the Logs page.
- Improved MQTT and Home Assistant connection status diagnostics in Settings.
- Added ownership labels to Compose services so the update process can distinguish HAMQTT containers from unrelated containers.
- Added `scripts/update.sh` for automatic consumer-safe updates:
  - Builds the application image.
  - Creates missing network and database volume resources.
  - Waits for PostgreSQL.
  - Applies pending Alembic migrations automatically.
  - Recreates only HAMQTT application containers.
  - Refuses to remove unrelated containers using HAMQTT container names.
  - Verifies the web health endpoint before reporting success.
- Compose now treats the existing HAMQTT network and PostgreSQL volume as persistent external resources.

## Database migrations

This release includes:

- `0003_application_logs`
- `0004_shared_mqtt_topic_objects`
- `0005_shared_mqtt_field_objects`

Migrations are applied automatically by `scripts/update.sh`; no manual migration command is required.

## Upgrade

From an existing installation:

```bash
git pull origin master
bash scripts/update.sh
```

The PostgreSQL container and `hamqtt-postgres-data` volume are preserved. Do not use `docker compose down -v` or remove the database volume during an upgrade.

## Validation

- 8 automated tests passing.
- `git diff --check` passing.
- Compose configuration rendering successfully.
- MQTT worker verified connecting and storing new messages after the storage fixes.
