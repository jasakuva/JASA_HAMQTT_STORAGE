#!/usr/bin/env bash
set -Eeuo pipefail

readonly DEFAULT_VERSION="latest"
readonly INSTALL_DIRECTORY_NAME="jasa_hamqtt_storage"
readonly PROJECT_NAME="hamqtt-store"
readonly APP_SERVICES=(web mqtt-ingestor ha-ingestor cleanup mcp backup recovery)
readonly CONTAINERS=(
    hamqtt-postgres
    hamqtt-redis
    hamqtt-migrate
    hamqtt-web
    hamqtt-mqtt-ingestor
    hamqtt-ha-ingestor
    hamqtt-cleanup
    hamqtt-mcp
    hamqtt-backup
    hamqtt-recovery
)

INSTALL_ROOT="$(pwd)"
INSTALL_DIR="$INSTALL_ROOT/$INSTALL_DIRECTORY_NAME"
VERSION="$DEFAULT_VERSION"
VERSION_SET=false
CREATED_INSTALL_DIR=false
SUDO=()

log() {
    printf '\n[hamqtt-install] %s\n' "$*"
}

fail() {
    printf '\n[hamqtt-install] ERROR: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<EOF
Usage: ./install.sh [VERSION]
       ./install.sh [--version VERSION]

Install HAMQTT Store into:
  $INSTALL_ROOT/$INSTALL_DIRECTORY_NAME

Examples:
  ./install.sh
  ./install.sh 0.3.3-rc2
  ./install.sh --version 0.3.3-rc2

Default version: $DEFAULT_VERSION
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            [[ $# -ge 2 ]] || fail "--version requires an image tag"
            [[ "$VERSION_SET" == false ]] || fail "Only one version may be supplied"
            VERSION="$2"
            VERSION_SET=true
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -* )
            fail "Unknown option: $1"
            ;;
        *)
            [[ "$VERSION_SET" == false ]] || fail "Only one version may be supplied"
            VERSION="$1"
            VERSION_SET=true
            shift
            ;;
    esac
done

[[ "$VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] \
    || fail "Invalid image version '$VERSION'"

# Refuse an existing installation before checking Docker or changing anything.
[[ ! -e "$INSTALL_DIR" ]] \
    || fail "$INSTALL_DIR already exists. Rename or remove it before performing a new installation. No files or containers were changed."

command -v docker >/dev/null 2>&1 || fail "Docker Engine is not installed"
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is not available"
docker info >/dev/null 2>&1 || fail "Docker daemon is not running or is not accessible"

if [[ "$(id -u)" != "0" ]]; then
    command -v sudo >/dev/null 2>&1 \
        || fail "sudo is required to assign the backup directory to UID/GID 999:999"
    sudo -v || fail "Unable to obtain sudo access for backup-directory permissions"
    SUDO=(sudo)
fi

for container in "${CONTAINERS[@]}"; do
    if docker container inspect "$container" >/dev/null 2>&1; then
        fail "Container '$container' already exists. Stop and remove or rename the existing HAMQTT installation before running this first-install script."
    fi
done

random_hex() {
    local bytes="$1"
    od -An -N "$bytes" -tx1 /dev/urandom | tr -d ' \n'
}

ensure_network() {
    local network="$1"
    if ! docker network inspect "$network" >/dev/null 2>&1; then
        log "Creating Docker network $network"
        docker network create --driver bridge "$network" >/dev/null
    fi
}

ensure_volume() {
    local volume="$1"
    if ! docker volume inspect "$volume" >/dev/null 2>&1; then
        log "Creating persistent Docker volume $volume"
        docker volume create "$volume" >/dev/null
    fi
}

wait_healthy() {
    local container="$1"
    local service="$2"
    local attempts="$3"
    local status
    local count

    for ((count = 1; count <= attempts; count++)); do
        status="$(docker container inspect --format '{{.State.Health.Status}}' "$container" 2>/dev/null || true)"
        if [[ "$status" == "healthy" ]]; then
            log "$container is healthy"
            return
        fi
        if [[ "$status" == "unhealthy" ]]; then
            break
        fi
        sleep 2
    done

    docker compose --project-name "$PROJECT_NAME" --project-directory "$INSTALL_DIR" \
        -f "$INSTALL_DIR/compose.yml" logs --tail 100 "$service" || true
    fail "$container did not become healthy"
}

verify_web() {
    local health_url="http://127.0.0.1:8000/health"
    local count

    for ((count = 1; count <= 30; count++)); do
        if command -v curl >/dev/null 2>&1 \
            && curl --fail --silent "$health_url" >/dev/null; then
            log "Web health check passed at $health_url"
            return
        fi
        if ! command -v curl >/dev/null 2>&1 \
            && docker exec hamqtt-web python -c \
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()" \
                >/dev/null 2>&1; then
            log "Web health check passed at $health_url"
            return
        fi
        sleep 2
    done

    docker compose --project-name "$PROJECT_NAME" --project-directory "$INSTALL_DIR" \
        -f "$INSTALL_DIR/compose.yml" logs --tail 100 web || true
    fail "Web service did not become healthy at $health_url"
}

on_error() {
    local exit_code=$?
    if [[ "$CREATED_INSTALL_DIR" == true ]]; then
        printf '\n[hamqtt-install] Installation stopped with exit status %s.\n' "$exit_code" >&2
        printf '[hamqtt-install] Diagnostic files were preserved in %s.\n' "$INSTALL_DIR" >&2
        printf '[hamqtt-install] No persistent volume was deleted.\n' >&2
    fi
    exit "$exit_code"
}
trap on_error ERR

log "Creating installation directory $INSTALL_DIR"
mkdir -p "$INSTALL_DIR/db/init" "$INSTALL_DIR/backups"
CREATED_INSTALL_DIR=true

cat >"$INSTALL_DIR/compose.yml" <<'COMPOSE_YAML'
services:
  redis:
    image: redis:7-alpine
    container_name: hamqtt-redis
    restart: unless-stopped
    networks:
      - hamqtt-store
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    labels:
      com.hamqtt.product: "hamqtt-store"
      com.hamqtt.service: "redis"

  postgres:
    image: ghcr.io/jasakuva/hamqtt-postgres-pgbackrest:${HAMQTT_VERSION:-latest}
    container_name: hamqtt-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-hamqtt_store}
      POSTGRES_USER: ${POSTGRES_USER:-hamqtt}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}
      PGDATA: /var/lib/postgresql/data/pgdata
    command:
      - postgres
      - -c
      - unix_socket_directories=/var/run/postgresql
      - -c
      - archive_mode=on
      - -c
      - archive_command=pgbackrest --stanza=hamqtt archive-push %p
    ports:
      - "${POSTGRES_BIND_IP:-127.0.0.1}:${POSTGRES_PORT:-5432}:5432"
    volumes:
      - ${POSTGRES_VOLUME:-hamqtt-postgres-data}:/var/lib/postgresql/data
      - hamqtt-postgres-socket:/var/run/postgresql
      - ${BACKUP_HOST_PATH:-./backups}:/var/lib/pgbackrest
      - ./pgbackrest.conf:/etc/pgbackrest/pgbackrest.conf:ro
      - ./db/init:/docker-entrypoint-initdb.d:ro
    networks:
      - hamqtt-store
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 20s
    labels:
      com.hamqtt.product: "hamqtt-store"
      com.hamqtt.service: "postgres"

  migrate:
    image: ghcr.io/jasakuva/hamqtt-store:${HAMQTT_VERSION:-latest}
    container_name: hamqtt-migrate
    environment:
      DATABASE_URL: postgresql+psycopg://hamqtt:${POSTGRES_PASSWORD}@hamqtt-postgres:5432/${POSTGRES_DB:-hamqtt_store}
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - hamqtt-store
    command: ["python", "-m", "alembic", "upgrade", "head"]
    labels:
      com.hamqtt.product: "hamqtt-store"
      com.hamqtt.service: "migrate"

  web:
    image: ghcr.io/jasakuva/hamqtt-store:${HAMQTT_VERSION:-latest}
    container_name: hamqtt-web
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+psycopg://hamqtt:${POSTGRES_PASSWORD}@hamqtt-postgres:5432/${POSTGRES_DB:-hamqtt_store}
      SECRET_KEY: ${SECRET_KEY:?Set SECRET_KEY in .env}
      APP_DATA_DIR: /app/data
      REDIS_URL: redis://redis:6379/0
      BACKUP_REPOSITORY_PATH: /var/lib/pgbackrest
      RECOVERY_MAX_UPLOAD_MB: ${RECOVERY_MAX_UPLOAD_MB:-1024}
      SESSION_DAYS: ${SESSION_DAYS:-365}
      SESSION_COOKIE_SECURE: ${SESSION_COOKIE_SECURE:-false}
    depends_on:
      migrate:
        condition: service_completed_successfully
      redis:
        condition: service_healthy
    ports:
      - "${APP_PORT:-8000}:8000"
    volumes:
      - ${APP_DATA_VOLUME:-hamqtt-app-data}:/app/data
      - ${BACKUP_HOST_PATH:-./backups}:/var/lib/pgbackrest:ro
    networks:
      - hamqtt-store
    labels:
      com.hamqtt.product: "hamqtt-store"
      com.hamqtt.service: "web"
    command: ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "hamqtt_store.wsgi:app"]

  mqtt-ingestor:
    image: ghcr.io/jasakuva/hamqtt-store:${HAMQTT_VERSION:-latest}
    container_name: hamqtt-mqtt-ingestor
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+psycopg://hamqtt:${POSTGRES_PASSWORD}@hamqtt-postgres:5432/${POSTGRES_DB:-hamqtt_store}
      REDIS_URL: redis://redis:6379/0
      APP_DATA_DIR: /app/data
    depends_on:
      migrate:
        condition: service_completed_successfully
      redis:
        condition: service_healthy
    networks:
      - hamqtt-store
    volumes:
      - ${APP_DATA_VOLUME:-hamqtt-app-data}:/app/data
    labels:
      com.hamqtt.product: "hamqtt-store"
      com.hamqtt.service: "mqtt-ingestor"
    command: ["python", "-m", "hamqtt_store.cli", "mqtt"]

  ha-ingestor:
    image: ghcr.io/jasakuva/hamqtt-store:${HAMQTT_VERSION:-latest}
    container_name: hamqtt-ha-ingestor
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+psycopg://hamqtt:${POSTGRES_PASSWORD}@hamqtt-postgres:5432/${POSTGRES_DB:-hamqtt_store}
      REDIS_URL: redis://redis:6379/0
      APP_DATA_DIR: /app/data
    depends_on:
      migrate:
        condition: service_completed_successfully
    networks:
      - hamqtt-store
    volumes:
      - ${APP_DATA_VOLUME:-hamqtt-app-data}:/app/data
    labels:
      com.hamqtt.product: "hamqtt-store"
      com.hamqtt.service: "ha-ingestor"
    command: ["python", "-m", "hamqtt_store.cli", "ha"]

  mcp:
    image: ghcr.io/jasakuva/hamqtt-store:${HAMQTT_VERSION:-latest}
    container_name: hamqtt-mcp
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+psycopg://hamqtt:${POSTGRES_PASSWORD}@hamqtt-postgres:5432/${POSTGRES_DB:-hamqtt_store}
      MCP_TRANSPORT: streamable-http
      APP_DATA_DIR: /app/data
    depends_on:
      migrate:
        condition: service_completed_successfully
    ports:
      - "${MCP_BIND_IP:-127.0.0.1}:${MCP_PORT:-8001}:8000"
    networks:
      - hamqtt-store
    volumes:
      - ${APP_DATA_VOLUME:-hamqtt-app-data}:/app/data
    labels:
      com.hamqtt.product: "hamqtt-store"
      com.hamqtt.service: "mcp"
    command: ["python", "-m", "hamqtt_store.cli", "mcp"]

  cleanup:
    image: ghcr.io/jasakuva/hamqtt-store:${HAMQTT_VERSION:-latest}
    container_name: hamqtt-cleanup
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+psycopg://hamqtt:${POSTGRES_PASSWORD}@hamqtt-postgres:5432/${POSTGRES_DB:-hamqtt_store}
      CLEANUP_HOUR_UTC: ${CLEANUP_HOUR_UTC:-2}
      CLEANUP_MINUTE_UTC: ${CLEANUP_MINUTE_UTC:-0}
      APP_DATA_DIR: /app/data
    depends_on:
      migrate:
        condition: service_completed_successfully
    networks:
      - hamqtt-store
    volumes:
      - ${APP_DATA_VOLUME:-hamqtt-app-data}:/app/data
    labels:
      com.hamqtt.product: "hamqtt-store"
      com.hamqtt.service: "cleanup"
    command: ["python", "-m", "hamqtt_store.cli", "cleanup"]

  backup:
    image: ghcr.io/jasakuva/hamqtt-backup-pgbackrest:${HAMQTT_VERSION:-latest}
    container_name: hamqtt-backup
    user: "999:999"
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+psycopg://hamqtt:${POSTGRES_PASSWORD}@hamqtt-postgres:5432/${POSTGRES_DB:-hamqtt_store}
      BACKUP_REPOSITORY_PATH: /var/lib/pgbackrest
      APP_DATA_DIR: /app/data
    depends_on:
      migrate:
        condition: service_completed_successfully
    network_mode: "service:postgres"
    volumes:
      - ${APP_DATA_VOLUME:-hamqtt-app-data}:/app/data
      - ${BACKUP_HOST_PATH:-./backups}:/var/lib/pgbackrest
      - ${POSTGRES_VOLUME:-hamqtt-postgres-data}:/var/lib/postgresql/data:ro
      - hamqtt-postgres-socket:/var/run/postgresql
      - ./pgbackrest.conf:/etc/pgbackrest/pgbackrest.conf:ro
    labels:
      com.hamqtt.product: "hamqtt-store"
      com.hamqtt.service: "backup"
    command: ["python", "-m", "hamqtt_store.cli", "backup"]

  recovery:
    image: ghcr.io/jasakuva/hamqtt-backup-pgbackrest:${HAMQTT_VERSION:-latest}
    container_name: hamqtt-recovery
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+psycopg://hamqtt:${POSTGRES_PASSWORD}@hamqtt-postgres:5432/${POSTGRES_DB:-hamqtt_store}
      POSTGRES_USER: ${POSTGRES_USER:-hamqtt}
      APP_DATA_DIR: /app/data
      BACKUP_REPOSITORY_PATH: /var/lib/pgbackrest
      RECOVERY_MAX_UPLOAD_MB: ${RECOVERY_MAX_UPLOAD_MB:-1024}
    depends_on:
      migrate:
        condition: service_completed_successfully
    networks:
      - hamqtt-store
    volumes:
      - ${APP_DATA_VOLUME:-hamqtt-app-data}:/app/data
      - ${BACKUP_HOST_PATH:-./backups}:/var/lib/pgbackrest
    labels:
      com.hamqtt.product: "hamqtt-store"
      com.hamqtt.service: "recovery"
    command: ["python", "-m", "hamqtt_store.cli", "recovery"]

networks:
  hamqtt-store:
    name: ${POSTGRES_NETWORK:-hamqtt-store-network}
    external: true

volumes:
  hamqtt-postgres-socket:
    name: hamqtt-postgres-socket
  hamqtt-app-data:
    name: ${APP_DATA_VOLUME:-hamqtt-app-data}
    external: true
  hamqtt-postgres-data:
    name: ${POSTGRES_VOLUME:-hamqtt-postgres-data}
    external: true
COMPOSE_YAML

cat >"$INSTALL_DIR/pgbackrest.conf" <<'PGBACKREST_CONF'
[global]
repo1-path=/var/lib/pgbackrest/hamqtt
repo1-retention-full=4
repo1-retention-diff=14
repo1-bundle=y
start-fast=y
log-level-console=info

[hamqtt]
pg1-path=/var/lib/postgresql/data/pgdata
pg1-port=5432
pg1-user=hamqtt
PGBACKREST_CONF

cat >"$INSTALL_DIR/db/init/001-enable-extensions.sql" <<'POSTGRES_INIT_SQL'
-- PostgreSQL initialization for HA MQTT Store.
-- This file is executed once when the PostgreSQL data volume is initialized.

CREATE EXTENSION IF NOT EXISTS vector;

COMMENT ON EXTENSION vector IS 'Vector similarity search for HA MQTT Store';
POSTGRES_INIT_SQL

POSTGRES_PASSWORD="$(random_hex 24)"
SECRET_KEY="$(random_hex 32)"

umask 077
cat >"$INSTALL_DIR/.env" <<EOF
HAMQTT_VERSION=$VERSION
POSTGRES_DB=hamqtt_store
POSTGRES_USER=hamqtt
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
SECRET_KEY=$SECRET_KEY
POSTGRES_BIND_IP=127.0.0.1
POSTGRES_PORT=5432
APP_PORT=8000
MCP_BIND_IP=127.0.0.1
MCP_PORT=8001
POSTGRES_VOLUME=hamqtt-postgres-data
APP_DATA_VOLUME=hamqtt-app-data
POSTGRES_NETWORK=hamqtt-store-network
BACKUP_HOST_PATH=./backups
RECOVERY_MAX_UPLOAD_MB=1024
SESSION_DAYS=365
SESSION_COOKIE_SECURE=false
CLEANUP_HOUR_UTC=2
CLEANUP_MINUTE_UTC=0
EOF
chmod 0600 "$INSTALL_DIR/.env"

cat >"$INSTALL_DIR/install-info" <<EOF
installed_version=$VERSION
installed_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
compose_project=$PROJECT_NAME
EOF
chmod 0644 "$INSTALL_DIR/install-info" "$INSTALL_DIR/compose.yml" \
    "$INSTALL_DIR/pgbackrest.conf" "$INSTALL_DIR/db/init/001-enable-extensions.sql"

"${SUDO[@]}" chown -R 999:999 "$INSTALL_DIR/backups"
chmod 0770 "$INSTALL_DIR/backups"

readonly COMPOSE=(
    docker compose
    --project-name "$PROJECT_NAME"
    --project-directory "$INSTALL_DIR"
    --env-file "$INSTALL_DIR/.env"
    -f "$INSTALL_DIR/compose.yml"
)

log "Validating Compose configuration for HAMQTT version $VERSION"
"${COMPOSE[@]}" config --quiet

ensure_network hamqtt-store-network
ensure_volume hamqtt-postgres-data
ensure_volume hamqtt-app-data

log "Pulling HAMQTT $VERSION and dependency images"
"${COMPOSE[@]}" pull

log "Starting PostgreSQL and Redis"
"${COMPOSE[@]}" up -d --no-deps postgres redis
wait_healthy hamqtt-postgres postgres 90
wait_healthy hamqtt-redis redis 60

log "Creating and validating the pgBackRest stanza"
"${COMPOSE[@]}" run --rm --no-deps backup \
    pgbackrest --stanza=hamqtt --log-level-file=off stanza-create
"${COMPOSE[@]}" run --rm --no-deps backup \
    pgbackrest --stanza=hamqtt --log-level-file=off check

log "Applying database migrations"
"${COMPOSE[@]}" run --rm --no-deps migrate

log "Starting HAMQTT application services"
"${COMPOSE[@]}" up -d --no-deps "${APP_SERVICES[@]}"
verify_web

backup_user="$(docker container inspect --format '{{.Config.User}}' hamqtt-backup)"
[[ "$backup_user" == "999:999" ]] \
    || fail "Backup container user is '$backup_user', expected '999:999'"

log "Installation completed successfully"
"${COMPOSE[@]}" ps -a
cat <<EOF

HAMQTT Store $VERSION is installed in:
  $INSTALL_DIR

Dashboard:
  http://localhost:8000

Management commands:
  cd "$INSTALL_DIR"
  docker compose --project-name $PROJECT_NAME ps -a
  docker compose --project-name $PROJECT_NAME logs --tail 100 web
  docker compose --project-name $PROJECT_NAME stop
  docker compose --project-name $PROJECT_NAME start

Configuration and generated secrets:
  $INSTALL_DIR/.env

Backup repository:
  $INSTALL_DIR/backups
EOF