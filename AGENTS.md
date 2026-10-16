# Repository Operating Instructions

These instructions apply to coding and deployment work in this repository.

## Container engine and Compose command

- The canonical container engine for this project is **Podman**.
- The canonical Compose command is **`podman-compose`**.
- Do not substitute `podman compose`, `docker compose`, `docker-compose`, or Docker Desktop commands unless the user explicitly requests that change.
- Before giving container instructions, verify the current working directory and use absolute paths when referring to project files.
- Keep the same engine and Compose command throughout a troubleshooting session. Do not change commands between responses without first explaining why and confirming the change.

## Safe container operations

- Inspect the current containers before removing or recreating anything.
- If a fixed container name is already in use, inspect it first and remove only the stale project container when appropriate.
- Never use `down -v`, `volume rm`, or any volume deletion command during normal startup, rebuild, upgrade, or recovery.
- Preserve `hamqtt-postgres-data` and `hamqtt-app-data` unless the user explicitly requests data deletion.
- When recreating containers, remove containers only; do not remove named volumes or the project network unless necessary.
- If a dependency graph is stale, use one consistent cleanup and recreation process rather than switching engines.

## Standard Podman workflow

Run commands from:

```text
C:\Users\janne\Documents\VS_HAMQTT_STORE
```

Typical commands are:

```powershell
Set-Location "C:\Users\janne\Documents\VS_HAMQTT_STORE"
podman machine start
podman-compose config
start-hamqtt.cmd
podman-compose ps -a
podman-compose logs --tail 100 web
```

For a controlled migration startup:

```powershell
podman-compose up -d postgres redis
podman-compose run --rm migrate
podman-compose up -d web mqtt-ingestor ha-ingestor cleanup mcp
```

## Recovery rules

1. Inspect `podman ps -a`, the relevant container, volumes, and network first.
2. Explain which containers will be removed.
3. Remove only stale HAMQTT containers with `podman rm -f` when necessary.
4. Never remove persistent volumes as part of recovery.
5. Recreate dependencies, run migrations, then start application services.
6. Verify Redis, container status, and `http://localhost:8000/health`.

## Coding-agent behavior

- Read relevant files before editing.
- Show a concise plan before making changes.
- Preserve existing project conventions.
- Use the available tools to validate edits.
- After editing, run tests, compilation checks, Compose validation, and `git diff --check` when applicable.
- Re-read edited files and report exactly what changed.
- Do not invent installation or deployment steps that were not verified in this repository.