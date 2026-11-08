# Release 0.3.4-rc3

Release date: 2026-11-08

HA MQTT Store `0.3.4-rc3` is a cumulative prerelease. It combines the RC1
time-aligned CSV export and MCP history aggregation features with the RC2
fresh-install, migration, installer, and updater fixes, plus the RC3 release
branch reconciliation and `.env` version-persistence fixes.

## Highlights

### Wide-format CSV export

- Selected Home Assistant entities and MQTT fields are exported as separate
  columns aligned by timestamp.
- Missing values remain empty; values are not forward-filled or interpolated.
- Timestamp aggregation to one-second buckets is enabled by default.
- The last chronological value is retained when duplicate values occur within a
  one-second bucket.
- Clear the aggregation checkbox to preserve exact timestamps, including
  milliseconds and microseconds.

### Read-only MCP history aggregation

- Raw history behavior remains backwards compatible.
- Time-bounded queries accept timezone-aware ISO-8601 timestamps and support
  cursor pagination.
- PostgreSQL performs `15m` and `1h` aggregation before results are returned.
- Supported methods are `avg`, `min`, `max`, `first`, `last`, `sum`, and
  `counter_delta`.
- Results include bucket boundaries, counts, coverage, validity, and missing-data
  markers.
- Counter-like units automatically use counter-delta handling where appropriate,
  while negative reset deltas are excluded.

### Installation and updates

- Fresh-install migrations are safe for new and partially initialized databases.
- The Linux installer creates protected `.env` files, persistent resources, and
  executable update/uninstall helpers.
- The updater pulls coordinated GHCR images, runs migrations before application
  services, preserves persistent volumes, and persists the selected
  `HAMQTT_VERSION` in `.env`.
- Normal updates do not use `down -v` and do not delete
  `hamqtt-postgres-data`, `hamqtt-app-data`, or the backup repository.

## Install the prerelease on a new Linux Docker host

```bash
wget -O install-hamqtt.sh \
  https://raw.githubusercontent.com/jasakuva/JASA_HAMQTT_STORAGE/master/deploy/install.sh
chmod +x install-hamqtt.sh
./install-hamqtt.sh --version 0.3.4-rc3
```

## Update an existing GHCR installation

```bash
cd /opt/JASA-HAMQTT-STORE/jasa_hamqtt_storage
sudo ./update-from-github.sh 0.3.4-rc3
grep '^HAMQTT_VERSION=' .env
docker compose --project-name hamqtt-store ps -a
curl -fsS http://localhost:8000/health
```

Expected version:

```text
HAMQTT_VERSION=0.3.4-rc3
```

## Published images

The prerelease publishes coordinated `linux/amd64` images:

- `ghcr.io/jasakuva/hamqtt-store:0.3.4-rc3`
- `ghcr.io/jasakuva/hamqtt-postgres-pgbackrest:0.3.4-rc3`
- `ghcr.io/jasakuva/hamqtt-backup-pgbackrest:0.3.4-rc3`

## Validation

- 61 Python tests passed.
- Python compilation passed.
- Root Compose configuration rendered successfully.
- Local Podman builds passed for all three images.
- GitHub Actions container publication completed successfully for all three
  images.
- `git diff --check` passed.

## Known limitations

- Published images target `linux/amd64`.
- The MCP aggregation slice currently targets numeric Home Assistant history
  values.
- Boolean/categorical aggregation, multi-entity aligned MCP aggregation, Nord
  Pool price normalization, and consumption-weighted price comparison remain
  future work.
- HTTPS termination, login throttling, audit logging, external secret
  management, fine-grained authorization, and authenticated MCP transport remain
  deployment or future hardening work.