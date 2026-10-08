# PostgreSQL and pgvector setup

This project currently runs PostgreSQL in its own Podman container. The setup is designed for Windows with Podman's Linux VM and is also suitable for Linux.

## Chosen image

```text
pgvector/pgvector:0.8.7-pg17-bookworm
```

The image contains PostgreSQL 17 and pgvector 0.8.7. The tag is pinned so that a future image update does not silently change the database engine or extension version.

## Files

- `.env.example`: configuration template.
- `.env`: local development configuration; do not commit it.
- `podman-compose.yml`: future multi-container definition; currently it contains PostgreSQL only.
- `db/init/001-enable-extensions.sql`: enables the `vector` extension during first database initialization.

## Start with Podman directly

From `C:\Users\janne\Documents\VS_HAMQTT_STORE`:

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

## Start with Compose provider

Podman 5's `podman compose` command is a wrapper around an external Compose provider. The installed `podman-compose` command may be used directly:

```powershell
podman-compose -f podman-compose.yml up -d postgres
```

The direct `podman run` method is the baseline because it does not depend on a Compose provider being available.

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

The hostname `hamqtt-postgres` works for later containers attached to `hamqtt-store-network`; `localhost` is for tools running on Windows.

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
