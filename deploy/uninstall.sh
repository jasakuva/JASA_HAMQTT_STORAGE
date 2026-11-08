#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_DIRECTORY_NAME="jasa_hamqtt_storage"
DEFAULT_INSTALL_DIR="$(pwd)/$INSTALL_DIRECTORY_NAME"
INSTALL_DIR="$DEFAULT_INSTALL_DIR"
DELETE_DATA=false
COMPOSE_BASE=()

CONTAINERS=(
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

log() {
    printf '[hamqtt-uninstall] %s\n' "$*"
}

fail() {
    printf '[hamqtt-uninstall] ERROR: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<EOF
Usage: sudo ./uninstall.sh [OPTIONS]

Remove the HAMQTT application from a Docker installation.

By default, containers, the HAMQTT network, and deployment files are removed.
Persistent Docker volumes, .env, and backups/ are preserved.

Options:
  --install-dir DIR  HAMQTT installation directory
  --delete-data      Also delete persistent volumes, backups/, .env, and the
                     complete installation directory. Requires typing DELETE.
  -h, --help         Show this help

Examples:
  sudo ./uninstall.sh
  sudo ./uninstall.sh --install-dir /opt/JASA-HAMQTT-STORE/jasa_hamqtt_storage
  sudo ./uninstall.sh --delete-data
EOF
}

detect_compose() {
    if docker compose version >/dev/null 2>&1; then
        COMPOSE_BASE=(docker compose)
        return
    fi
    if command -v docker-compose >/dev/null 2>&1 \
        && docker-compose version >/dev/null 2>&1; then
        COMPOSE_BASE=(docker-compose)
        return
    fi
    fail "Docker Compose is not available. Install Docker Compose v2 ('docker compose') or Docker Compose v1 ('docker-compose')."
}

container_exists() {
    docker container inspect "$1" >/dev/null 2>&1
}

container_image() {
    docker container inspect --format '{{.Config.Image}}' "$1" 2>/dev/null || true
}

container_is_hamqtt() {
    local name="$1"
    local image
    image="$(container_image "$name")"
    case "$name" in
        hamqtt-postgres)
            [[ "$image" == localhost/hamqtt-postgres-pgbackrest:* \
                || "$image" == ghcr.io/jasakuva/hamqtt-postgres-pgbackrest:* \
                || "$image" == *pgvector* ]]
            ;;
        hamqtt-redis)
            [[ "$image" == redis:* || "$image" == */redis:* ]]
            ;;
        hamqtt-backup|hamqtt-recovery)
            [[ "$image" == localhost/hamqtt-backup-pgbackrest:* \
                || "$image" == ghcr.io/jasakuva/hamqtt-backup-pgbackrest:* ]]
            ;;
        *)
            [[ "$image" == localhost/hamqtt-store:* \
                || "$image" == ghcr.io/jasakuva/hamqtt-store:* ]]
            ;;
    esac
}

check_container_ownership() {
    local name
    for name in "${CONTAINERS[@]}"; do
        if container_exists "$name" && ! container_is_hamqtt "$name"; then
            fail "Container '$name' is not recognized as HAMQTT (image: $(container_image "$name")). Refusing to remove it."
        fi
    done
}

confirm_delete_data() {
    local confirmation
    printf 'This will permanently delete HAMQTT database/application volumes, backups, .env, and installation files.\n'
    printf 'Type DELETE to continue: '
    read -r confirmation
    [[ "$confirmation" == "DELETE" ]] \
        || fail "Confirmation did not match DELETE; no persistent data was removed"
}

remove_volumes() {
    local volume
    local postgres_volume="${POSTGRES_VOLUME:-hamqtt-postgres-data}"
    local app_data_volume="${APP_DATA_VOLUME:-hamqtt-app-data}"
    for volume in "$postgres_volume" "$app_data_volume" hamqtt-postgres-socket; do
        if docker volume inspect "$volume" >/dev/null 2>&1; then
            log "Removing Docker volume $volume"
            docker volume rm "$volume" >/dev/null
        fi
    done
}

remove_deployment_files() {
    if [[ "$DELETE_DATA" == true ]]; then
        log "Removing complete installation directory $INSTALL_DIR"
        rm -rf -- "$INSTALL_DIR"
        return
    fi

    log "Removing deployment files while preserving .env and backups/"
    rm -f -- \
        "$INSTALL_DIR/compose.yml" \
        "$INSTALL_DIR/update-from-github.sh" \
        "$INSTALL_DIR/install-info" \
        "$INSTALL_DIR/pgbackrest.conf"
    rm -rf -- "$INSTALL_DIR/db"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --install-dir)
            [[ $# -ge 2 ]] || fail "--install-dir requires a directory"
            INSTALL_DIR="$2"
            shift 2
            ;;
        --delete-data)
            DELETE_DATA=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "Unknown option: $1"
            ;;
    esac
done

[[ "$(id -u)" == "0" ]] \
    || fail "This script must be run as root. Re-run it with: sudo $0"
[[ -d "$INSTALL_DIR" ]] \
    || fail "Installation directory does not exist: $INSTALL_DIR"
[[ -f "$INSTALL_DIR/compose.yml" || "$DELETE_DATA" == true ]] \
    || fail "Not a HAMQTT installation directory: $INSTALL_DIR"

command -v docker >/dev/null 2>&1 || fail "Docker Engine is not installed"
detect_compose
if [[ "$DELETE_DATA" == true ]]; then
    confirm_delete_data
fi

check_container_ownership

log "Stopping and removing HAMQTT containers without deleting volumes"
"${COMPOSE_BASE[@]}" --project-name hamqtt-store --project-directory "$INSTALL_DIR" \
    -f "$INSTALL_DIR/compose.yml" down --remove-orphans 2>/dev/null || true

for container in "${CONTAINERS[@]}"; do
    if container_exists "$container"; then
        log "Removing HAMQTT container $container"
        docker rm -f "$container" >/dev/null
    fi
done

NETWORK="${POSTGRES_NETWORK:-hamqtt-store-network}"
if [[ -f "$INSTALL_DIR/.env" ]]; then
    configured_network="$(sed -n 's/^POSTGRES_NETWORK=//p' "$INSTALL_DIR/.env" | tail -n 1)"
    [[ -n "$configured_network" ]] && NETWORK="$configured_network"
    configured_postgres_volume="$(sed -n 's/^POSTGRES_VOLUME=//p' "$INSTALL_DIR/.env" | tail -n 1)"
    [[ -n "$configured_postgres_volume" ]] && POSTGRES_VOLUME="$configured_postgres_volume"
    configured_app_data_volume="$(sed -n 's/^APP_DATA_VOLUME=//p' "$INSTALL_DIR/.env" | tail -n 1)"
    [[ -n "$configured_app_data_volume" ]] && APP_DATA_VOLUME="$configured_app_data_volume"
fi
if docker network inspect "$NETWORK" >/dev/null 2>&1; then
    log "Removing HAMQTT network $NETWORK"
    docker network rm "$NETWORK" >/dev/null || true
fi

if [[ "$DELETE_DATA" == true ]]; then
    remove_volumes
else
    log "Preserving Docker volumes hamqtt-postgres-data and hamqtt-app-data"
fi

remove_deployment_files
log "HAMQTT uninstall completed"