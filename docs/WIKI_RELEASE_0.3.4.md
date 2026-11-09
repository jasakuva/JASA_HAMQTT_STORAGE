# Release 0.3.4

Release date: 2026-11-09

HA MQTT Store `0.3.4` is the stable release of the cumulative 0.3.4 feature
line. It was validated through the `0.3.4-rc1` through `0.3.4-rc4`
prerelease cycle.

## Highlights

### MCP history access

- `get_home_assistant_history` is the backwards-compatible raw-history tool.
- `get_home_assistant_history_aggregated` is the dedicated aggregation tool.
- Required aggregation arguments are `entity_id`, timezone-aware ISO-8601
  `start`, `end`, and `interval`.
- Supported intervals are `15m` and `1h`.
- Supported methods are `avg`, `min`, `max`, `first`, `last`, `sum`, and
  `counter_delta`.
- PostgreSQL performs aggregation server-side and returns bucket quality,
  coverage, and missing-data metadata.
- The PostgreSQL `statement_timeout` execution error is fixed.

### CSV export and deployment

- Wide-format CSV export aligns selected datasets by timestamp.
- Fresh-install migrations and updater behavior are safe for persistent data.
- Normal updates preserve `hamqtt-postgres-data`, `hamqtt-app-data`, and backups.

## Example aggregated MCP call

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

## Install a fixed stable version

```bash
wget -O install-hamqtt.sh \
  https://raw.githubusercontent.com/jasakuva/JASA_HAMQTT_STORAGE/master/deploy/install.sh
chmod +x install-hamqtt.sh
./install-hamqtt.sh --version 0.3.4
```

## Update an existing installation

```bash
cd /opt/JASA-HAMQTT-STORE/jasa_hamqtt_storage
sudo ./update-from-github.sh 0.3.4
grep '^HAMQTT_VERSION=' .env
docker compose --project-name hamqtt-store ps -a
curl -fsS http://localhost:8000/health
```

For production, prefer the immutable `0.3.4` tag over `latest`. The `latest`
tag points to the newest stable release and does not move for prereleases.

Do not use `down -v` during routine updates.

## Published images

- `ghcr.io/jasakuva/hamqtt-store:0.3.4`
- `ghcr.io/jasakuva/hamqtt-store:latest`
- `ghcr.io/jasakuva/hamqtt-postgres-pgbackrest:0.3.4`
- `ghcr.io/jasakuva/hamqtt-postgres-pgbackrest:latest`
- `ghcr.io/jasakuva/hamqtt-backup-pgbackrest:0.3.4`
- `ghcr.io/jasakuva/hamqtt-backup-pgbackrest:latest`

## Validation

- 62 Python tests passed.
- Python compilation passed.
- Root Compose configuration rendered successfully.
- `git diff --check` passed.