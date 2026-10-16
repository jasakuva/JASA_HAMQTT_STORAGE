# Release 0.3.2

Release date: 2026-10-16

HA MQTT Store 0.3.2 improves backup portability and control, makes graph range
selection reliable, and removes Zigbee2MQTT bridge/system topics from Graph and
Export selectors without deleting stored MQTT data.

## Highlights

- Stable HTML graph range controls for `1h`, `6h`, `1d`, and `all`.
- `zigbee2mqtt/bridge` and descendant topics are hidden from the shared Graph
  and Export selector catalog.
- Normal Zigbee2MQTT device topics remain selectable.
- Existing bridge-topic raw messages and observations remain stored.
- Backup schedule and retention are configured with independent low, medium,
  and high profiles.
- Manual portable PostgreSQL custom-format dumps are available.
- Portable dumps can optionally be scheduled daily and are covered by the
  selected retention profile.

## Upgrade

```bash
git fetch origin
git checkout v0.3.2
bash scripts/update.sh
```

The update workflow runs migrations before application services and preserves
the PostgreSQL data volume, application data volume, and configured backup
repository. Never use `down -v` during a routine upgrade.

## Graph and Export behavior

The Graph page continues to support Plotly zooming, panning, scroll zoom, and
the range slider. The `1h`, `6h`, `1d`, and `all` controls are now normal HTML
buttons so they remain stable across Plotly redraws.

The shared Graph/Export catalog omits `zigbee2mqtt/bridge` and its descendants.
This is presentation-layer filtering only: it does not remove stored MQTT
messages or observations. If an older bookmarked graph URL references a now
filtered object ID, reopen `/graph` without the stale query parameter.

## Backup behavior

Backup settings provide separate schedule and retention profiles. The schedule
profile controls full and differential pgBackRest intervals, while the
retention profile controls retained pgBackRest full sets and portable dumps.
Portable dumps use PostgreSQL's compressed custom format without owner metadata
and can be created manually or once per day when enabled.

## Validation

- 33 automated tests passed.
- Python compilation passed.
- Documentation validation passed.
- Compose configuration passed.
- `git diff --check` passed.
- The recreated web container reported healthy at `/health`.

## Known limitations

This release remains intended for controlled local/LAN deployments. Fine-grained
authorization, HTTPS/TLS deployment, login throttling, audit logging, external
secret management, and authenticated MCP transport remain security work items.