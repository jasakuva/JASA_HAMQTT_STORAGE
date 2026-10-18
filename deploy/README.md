# HAMQTT Store Linux installer

`install.sh` is a self-contained, single-file installer. It creates a new Docker Compose installation in
`./jasa_hamqtt_storage`, relative to the directory from which the installer is
run. It pulls published images from GHCR; it does not build the application from
source.

## Requirements

- Linux
- Docker Engine
- Docker Compose v2 (`docker compose`)
- `sudo` when the current user is not root

The installer uses `sudo` only to assign the bind-mounted pgBackRest repository
to UID/GID `999:999`, the PostgreSQL filesystem identity used by the published
images.

## Install the latest release

From the directory that should contain the new installation:

With `wget`:

```bash
wget -O install-hamqtt.sh \
  https://raw.githubusercontent.com/jasakuva/JASA_HAMQTT_STORAGE/master/deploy/install.sh
chmod +x install-hamqtt.sh
./install-hamqtt.sh
```

Or with `curl`:

```bash
curl -fsSLo install-hamqtt.sh \
  https://raw.githubusercontent.com/jasakuva/JASA_HAMQTT_STORAGE/master/deploy/install.sh
chmod +x install-hamqtt.sh
./install-hamqtt.sh
```

Only `install-hamqtt.sh` needs to be downloaded. The installer writes the
Compose file, pgBackRest configuration, PostgreSQL initialization SQL, `.env`,
and installation metadata itself.

For example, running the installer from `/opt` creates:

```text
/opt/jasa_hamqtt_storage
```

## Install a specific image version

Either form is accepted:

```bash
./install-hamqtt.sh --version 0.3.3
./install-hamqtt.sh 0.3.3
```

The default version is `latest`, so running the installer without an argument
pulls the current stable images published by the latest non-prerelease GitHub
release.

## Installed files

```text
jasa_hamqtt_storage/
├── compose.yml
├── .env
├── install-info
├── pgbackrest.conf
├── backups/
└── db/
    └── init/
        └── 001-enable-extensions.sql
```

`.env` contains generated database and session secrets and is created with mode
`0600`. Do not publish or share it.

The installer stops without changing Docker or filesystem state if
`./jasa_hamqtt_storage` already exists. Rename or remove that directory manually
before performing another first installation. Do not remove an active
installation directory unless its backup repository and `.env` have been
preserved.

## Management

Run Compose commands from the installed directory:

```bash
cd ./jasa_hamqtt_storage
docker compose --project-name hamqtt-store ps -a
docker compose --project-name hamqtt-store logs --tail 100 web
docker compose --project-name hamqtt-store stop
docker compose --project-name hamqtt-store start
```

The PostgreSQL database and application data use the persistent named volumes
`hamqtt-postgres-data` and `hamqtt-app-data`. The pgBackRest repository is stored
in the installation's `backups/` directory. Normal management must not use
`docker compose down -v` or delete these volumes.

PostgreSQL and MCP bind to loopback by default. The web dashboard is available
at `http://localhost:8000` after installation.