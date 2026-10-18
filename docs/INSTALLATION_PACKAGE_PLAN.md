# HAMQTT Store One-Command Installation Package Plan

**Status:** Initial Linux Docker installer implemented in `deploy/`. Windows and
the broader runtime-management wrapper remain planned.

## Goal

Allow a new user to install and start the complete HAMQTT Store stack with one command. The installer should ask for basic configuration, create the environment files, pull the required images, run migrations, start the stack, and print the dashboard URL.

Future Windows example:

```powershell
irm https://raw.githubusercontent.com/<owner>/<repo>/main/install.ps1 | iex
```

Future Linux/macOS example:

```bash
curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/main/install.sh | bash
```

## Proposed package layout

Create a separate deployment area:

```text
deploy/
├── compose.yml
├── .env.example
├── install.ps1
├── install.sh
├── hamqtt.ps1
├── hamqtt
└── README.md
```

The current root `compose.yml` should remain useful for development. The future `deploy/compose.yml` should be optimized for published installations.

## Published application image

The end-user Compose file should use a published image instead of building from source:

```yaml
image: ${HAMQTT_IMAGE:-ghcr.io/<owner>/hamqtt-store:latest}
```

Use the same application image for `migrate`, `web`, `mqtt-ingestor`, `ha-ingestor`, `mcp`, and `cleanup`. PostgreSQL/pgvector and Redis remain separate upstream images.

Add a future workflow at `.github/workflows/container.yml` to publish release images such as `ghcr.io/<owner>/hamqtt-store:0.3.0` and `ghcr.io/<owner>/hamqtt-store:latest`. Prefer fixed versions for predictable upgrades and rollback.

## Installation environment

Create a deployment `.env.example` containing:

```dotenv
HAMQTT_IMAGE=ghcr.io/<owner>/hamqtt-store:latest
POSTGRES_DB=hamqtt_store
POSTGRES_USER=hamqtt
POSTGRES_PASSWORD=
SECRET_KEY=
APP_PORT=8000
POSTGRES_PORT=5432
MCP_PORT=8001
POSTGRES_VOLUME=hamqtt-postgres-data
APP_DATA_VOLUME=hamqtt-app-data
POSTGRES_NETWORK=hamqtt-store-network
REDIS_URL=redis://redis:6379/0
SESSION_DAYS=365
SESSION_COOKIE_SECURE=false
```

The installer should generate `POSTGRES_PASSWORD` and `SECRET_KEY` unless supplied by the user. It must not commit or print secrets. On Linux/macOS, use `chmod 600 .env`.

## Compose deployment

The deployment Compose file must support Podman Compose and Docker Compose. It should define Redis, PostgreSQL/pgvector, migrations, web, MQTT ingestion, Home Assistant ingestion, cleanup, and optional MCP services.

Expected startup relationship:

```text
Redis ───────────────┐
                     │
PostgreSQL → migrate ├── web
                     ├── mqtt-ingestor
                     ├── ha-ingestor
                     ├── cleanup
                     └── mcp
```

Application services must start only after migrations succeed. PostgreSQL and Redis need health checks.

## Windows installer

Future file: `deploy/install.ps1`.

Responsibilities: check Podman and optionally Docker; check Compose support; initialize and start the Podman machine; ask for installation path, ports, database credentials, image version, and MCP preference; create `.env`; generate secure secrets; pull images; start PostgreSQL and Redis; wait for health checks; run migrations; start application services; wait for `/health`; and print the dashboard URL and management commands.

Example prompts:

```text
Installation directory [C:\ProgramData\hamqtt-store]:
Application port [8000]:
PostgreSQL port [5432]:
MCP port [8001]:
PostgreSQL username [hamqtt]:
PostgreSQL password:
Install MCP service? [y/N]:
Image version [latest]:
```

Support non-interactive options such as:

```powershell
.\install.ps1 -InstallPath "C:\ProgramData\hamqtt-store" -AppPort 8000 -PostgresPort 5432 -EnableMcp:$false
```

## Linux installer

Implemented as the self-contained, single-download `deploy/install.sh` for
Docker Engine with Docker Compose v2. It
creates `./jasa_hamqtt_storage`, generates `.env`, restricts its permissions,
generates the deployment files, creates the pgBackRest repository with UID/GID
`999:999`, pulls images, starts
dependencies, validates pgBackRest, runs migrations, starts services, verifies
health, and prints management commands. `latest` is the default image tag and a
different tag can be supplied with `--version` or as a positional argument.

## Runtime management commands

Provide `deploy/hamqtt.ps1` and `deploy/hamqtt` with commands for `install`, `start`, `stop`, `restart`, `status`, `logs`, `update`, `backup`, `restore`, and `uninstall`. Also support selecting service logs, for example `logs web` and `logs mqtt-ingestor`.

Normal commands must preserve PostgreSQL and application-data volumes. Destructive operations must require explicit confirmation.

## Upgrade behavior

The update command should pull the new deployment files and application image, start dependencies, run migrations before replacing application services, recreate the services, and verify the web health endpoint. If migration or health verification fails, stop safely without deleting persistent data.

The root `hamqtt.sh` launcher now provides shared source-checkout management for
Podman and Docker. A future published installation can reuse its engine-selection
and safe-volume behavior while replacing local builds with published image pulls.

## Backup and uninstall

Add a backup command that uses `pg_dump` from a temporary PostgreSQL client container or an available local client. Write timestamped files such as `backups/hamqtt_store_2026-10-12_184500.sql`.

Normal uninstall removes containers, the network, and deployment files but preserves data volumes. A separate `uninstall --delete-data` operation must require a confirmation phrase such as `DELETE` before removing volumes.

## Documentation

Add or update `docs/INSTALLATION.md`, `docs/UPGRADING.md`, `docs/BACKUP_AND_RESTORE.md`, `README.md`, and `docs/RESTART_GUIDE.md`. Document Windows Podman, Linux Podman, Docker fallback, ports, generated files, service status, logs, backup/restore, upgrades, uninstallation, troubleshooting, Redis, PostgreSQL persistence, and MCP configuration.

## Testing and validation

Static checks:

```bash
python -m compileall -q src
pytest -q
git diff --check
```

Compose checks:

```bash
podman compose config
docker compose config
```

Test fresh installation, existing `.env`, existing volumes and containers, missing engines, Docker fallback, port conflicts, failed migrations, Redis/PostgreSQL health failures, rerunning the installer, upgrades, safe uninstall, and explicit data deletion.

Acceptance criteria: a user runs one installer command, answers basic prompts, reaches the dashboard URL, survives a machine restart, can inspect status, can update without losing PostgreSQL data, and can back up and restore the database.

## Recommended implementation order

1. Refactor Compose to support published images.
2. Add the deployment Compose file.
3. Add `.env` generation and secret handling.
4. Add the PowerShell installer.
5. Add the Linux/macOS installer.
6. Add management wrappers.
7. Add GitHub Actions image publishing.
8. Add backup and restore commands.
9. Add documentation.
10. Test fresh installation and upgrades.

## Design decision

The future flow is:

```text
Installer package → generated .env → Podman/Docker Compose → published HAMQTT image → PostgreSQL + Redis + application services
```

The source-based root Compose file remains for development. The future `deploy/compose.yml` is for end users and published releases.