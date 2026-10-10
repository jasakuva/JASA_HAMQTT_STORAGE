# PostgreSQL and pgvector setup

This project runs PostgreSQL as part of the Docker Compose stack. The setup is also compatible with Podman Compose providers.

## Chosen image

```text
pgvector/pgvector:0.8.7-pg17-bookworm
```

The image contains PostgreSQL 17 and pgvector 0.8.7. The tag is pinned so that a future image update does not silently change the database engine or extension version.

## Files

- `.env.example`: configuration template.
- `.env`: local development configuration; do not commit it.
- `compose.yml`: PostgreSQL, migration, web, MQTT, Home Assistant, and MCP services.
- `db/init/001-enable-extensions.sql`: enables the `vector` extension during first database initialization.

## Start with Podman directly

From `%INSTALL_PATH%` (the local repository directory):

```powershell
podman machine start podman-machine-default
podman pull pgvector/pgvector:0.8.7-pg17-bookworm
podman network exists hamqtt-store-network; if ($LASTEXITCODE -ne 0) { podman network create hamqtt-store-network }
podman volume exists hamqtt-postgres-data; if ($LASTEXITCODE -ne 0) { podman volume create hamqtt-postgres-data }
podman run -d `
  --name hamqtt-postgres `
  --restart unless-stopped `
  --network hamqtt-store-network `
  -p 5432:5432 `
  -e POSTGRES_DB=hamqtt_store `
  -e POSTGRES_USER=hamqtt `
  -e POSTGRES_PASSWORD=hamqtt-local-development-password `
  -e PGDATA=/var/lib/postgresql/data/pgdata `
  -v hamqtt-postgres-data:/var/lib/postgresql/data `
  -v ${PWD}/db/init:/docker-entrypoint-initdb.d:ro `
  --health-cmd="pg_isready -U hamqtt -d hamqtt_store" `
  --health-interval=10s `
  --health-timeout=5s `
  --health-retries=10 `
  --health-start-period=20s `
  pgvector/pgvector:0.8.7-pg17-bookworm
```

The initialization SQL runs only when the named volume is empty.

## Start with Compose

Docker Compose automatically starts PostgreSQL, waits for its health check, runs migrations, and starts the application services after migration succeeds:

```bash
docker compose up -d
```

The same `compose.yml` can be used with a compatible Podman Compose provider if required by the host environment.

## Verify

```powershell
podman ps
podman inspect --format '{{.State.Health.Status}}' hamqtt-postgres
podman exec hamqtt-postgres pg_isready -U hamqtt -d hamqtt_store
type db\verify\001-verify.sql | podman exec -i hamqtt-postgres psql -U hamqtt -d hamqtt_store
```

Expected vector result:

```text
 extname | extversion
---------+------------
 vector  | 0.8.7
```

## Connection details for the future Python application

Inside the Podman network:

```text
postgresql+psycopg://hamqtt:hamqtt-local-development-password@hamqtt-postgres:5432/hamqtt_store
```

From Windows host processes:

```text
postgresql+psycopg://hamqtt:hamqtt-local-development-password@localhost:5432/hamqtt_store
```

From the Linux host or a trusted machine on the internal network, replace
`localhost` with the Docker host's LAN IP address, for example:

```text
postgresql+psycopg://hamqtt:<password>@192.168.1.20:5432/hamqtt_store
```

The Compose port mapping binds to `0.0.0.0` by default, so the host firewall
must allow TCP port `5432` from the intended internal subnet. Set
`POSTGRES_BIND_IP=127.0.0.1` in `.env` if database access should remain local
to the host. Do not expose this port directly to the public internet.

The hostname `hamqtt-postgres` works for containers attached to
`hamqtt-store-network`; `localhost` is for tools running on the host itself.

## Stop and remove

Stop/remove the container while preserving data:

```powershell
podman stop hamqtt-postgres
podman rm hamqtt-postgres
```

Delete the database data as well only when intentionally resetting development state:

```powershell
podman volume rm hamqtt-postgres-data
```
