# HAMQTT Store Linux installer

`install.sh` is a self-contained, single-file installer. It creates a new Docker Compose installation in
`./jasa_hamqtt_storage`, relative to the directory from which the installer is
run. It pulls published images from GHCR; it does not build the application from
source. After installation, the installer downloads the separate
`update-from-github.sh` and `uninstall.sh` scripts into the installation folder.

## Requirements

- Linux
- Docker Engine
- Docker Compose v2 (`docker compose`) or Docker Compose v1 (`docker-compose`)
- root access (`sudo`)

Run the installer with `sudo`, for example `sudo ./install-hamqtt.sh`. The
installer checks this before changing Docker or filesystem state and prefers
`docker compose`, falling back to `docker-compose` when necessary.

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
installation metadata, and downloads executable `update-from-github.sh` and
`uninstall.sh` helpers into the installation folder.

For example, running the installer from `/opt` creates:

```text
/opt/jasa_hamqtt_storage
```

## Install a specific image version

Either form is accepted:

```bash
./install-hamqtt.sh --version 0.3.4-rc3
./install-hamqtt.sh 0.3.4-rc3
```

The default version is `latest`, so running the installer without an argument
pulls the current stable images published by the latest non-prerelease GitHub
release.

## Installed files

```text
jasa_hamqtt_storage/
├── compose.yml
├── update-from-github.sh
├── uninstall.sh
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

## Uninstall

The uninstall script is safe by default. It removes HAMQTT containers, the
HAMQTT network, and deployment files while preserving `.env`, `backups/`, and
the persistent Docker volumes:

```bash
sudo ./uninstall.sh --install-dir /opt/JASA-HAMQTT-STORE/jasa_hamqtt_storage
```

To permanently remove the database, application data, backups, `.env`, and the
installation directory, pass `--delete-data`. The script requires typing
`DELETE` before it removes persistent data:

```bash
sudo ./uninstall.sh \
  --install-dir /opt/JASA-HAMQTT-STORE/jasa_hamqtt_storage \
  --delete-data
```

## Management

Run Compose commands from the installed directory:

```bash
cd ./jasa_hamqtt_storage
sudo ./update-from-github.sh              # update to the current latest images
sudo ./update-from-github.sh 0.3.4-rc3    # update to the RC3 image tag
# Use `docker compose` when Compose v2 is installed, otherwise use
# `docker-compose` for Compose v1.
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

The installed update and uninstall helpers resolve `compose.yml`, `.env`, and
the installation directory from their own script location. They can therefore
be run from any working directory, for example:

```bash
sudo /opt/JASA-HAMQTT-STORE/jasa_hamqtt_storage/update-from-github.sh 0.3.4-rc3
sudo /opt/JASA-HAMQTT-STORE/jasa_hamqtt_storage/uninstall.sh
```

The update helper does not delete the persistent PostgreSQL or application-data
volumes.