# HA MQTT Store 0.2.0

Release date: 2026-10-10

## Highlights

Version 0.2.0 adds read-only MCP access and significantly improves the operational and database documentation for HA MQTT Store.

## Added

- Read-only MCP server for Home Assistant, MQTT, object-catalog, and history data.
- Streamable HTTP MCP transport on the local `/mcp` endpoint.
- MCP enablement and read-only access controls in the Settings page.
- Sensitive-key redaction for MCP JSON and text responses.
- MCP tools for:
  - System summaries.
  - Object search and lookup.
  - Home Assistant entity state and history.
  - MQTT topics, fields, current values, and recent raw messages.
- MCP resources for summary and Home Assistant entity access.
- ChatGPT Personal and Codex setup instructions.
- ngrok tunneling instructions for temporary ChatGPT HTTPS access.
- Detailed PostgreSQL schema documentation based on the implemented SQLAlchemy models.
- Database ER diagram and database-domain overview diagram.
- SQL examples for HA state, MQTT lineage, parser failures, object links, retention review, and pgvector search.
- Reproducible architecture `.docx` generation through `tools/generate_architecture_docx.py`.
- Generic `%INSTALL_PATH%` documentation placeholders to avoid machine-specific paths.
- MCP unit tests covering registration, access checks, redaction, and query limits.

## Changed

- Project version updated from `0.1.0` to `0.2.0`.
- Architecture documentation now distinguishes implemented schema from planned extensions.
- Documentation validation now checks the implemented schema, MCP access, and SQL examples.
- Compose configuration includes the `hamqtt-mcp` service on host port `8001`.

## Security and operational notes

- MCP access is read-only and does not publish MQTT messages, call Home Assistant services, or write to the database.
- The current MCP HTTP endpoint is unauthenticated. When using ngrok, keep the tunnel active only for the required session and stop it with `Ctrl+C` afterward.
- Authentication, CSRF protection, authorization, and stronger production secret management remain future hardening work.

## Validation

The release was verified with:

- 8 automated tests passing.
- Python source compilation passing.
- Documentation validation passing.
- Architecture Word document regeneration passing.
- `git diff --check` passing.

## Upgrade notes

For an existing Podman installation:

```powershell
git pull origin master
podman build -t localhost/hamqtt-store:dev .
podman-compose --in-pod false up -d postgres migrate web mqtt-ingestor ha-ingestor mcp
```

Enable MCP read access at `http://localhost:8000/settings` before using the MCP service. Existing PostgreSQL data remains in the named `hamqtt-postgres-data` volume.