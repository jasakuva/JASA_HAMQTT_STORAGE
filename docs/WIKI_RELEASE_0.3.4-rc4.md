# Release 0.3.4-rc4

Release date: 2026-11-09

RC4 is a corrective prerelease for the cumulative 0.3.4 line. It includes the
RC1 CSV export and MCP aggregation features, RC2 installation and migration
fixes, RC3 updater and release reconciliation work, and fixes for MCP agent
discoverability and PostgreSQL aggregation execution.

## MCP changes

- Added the dedicated `get_home_assistant_history_aggregated` tool.
- Required arguments are visible in the MCP schema:
  - `entity_id`
  - timezone-aware ISO-8601 `start`
  - timezone-aware ISO-8601 `end`
  - `interval`, exactly `15m` or `1h`
- Optional arguments are `aggregation_method`, `cursor`, and `page_size`.
- Supported methods are `avg`, `min`, `max`, `first`, `last`, `sum`, and
  `counter_delta`.
- `get_home_assistant_history` now exposes only raw newest-first history with
  `entity_id` and `limit`.
- Fixed PostgreSQL `statement_timeout` execution. The previous parameterized
  `SET LOCAL` statement generated invalid SQL such as `SET LOCAL
  statement_timeout = $1`.

## Example aggregated call

```json
{
  "entity_id": "sensor.energy_usage",
  "start": "2026-11-01T00:00:00Z",
  "end": "2026-11-02T00:00:00Z",
  "interval": "15m",
  "aggregation_method": "avg",
  "page_size": 100
}
```

## Update an existing production installation

For the two-file Compose deployment, use both the base file and the GHCR image
override:

```bash
cd /opt/jasa-hamqtt-store

if grep -q '^HAMQTT_VERSION=' .env; then
    sed -i 's/^HAMQTT_VERSION=.*/HAMQTT_VERSION=0.3.4-rc4/' .env
else
    printf '\nHAMQTT_VERSION=0.3.4-rc4\n' >> .env
fi

docker compose \
  -p hamqtt-store \
  -f compose.yml \
  -f compose.github.yml \
  pull mcp

docker compose \
  -p hamqtt-store \
  -f compose.yml \
  -f compose.github.yml \
  up -d --force-recreate mcp
```

Verify the MCP image and logs:

```bash
docker compose -p hamqtt-store -f compose.yml -f compose.github.yml ps -a
docker compose -p hamqtt-store -f compose.yml -f compose.github.yml logs --tail 100 mcp
```

Do not use `down -v`; persistent database and application volumes must remain.

## Validation

- 62 Python tests passed.
- Python compilation passed.
- `git diff --check` passed.