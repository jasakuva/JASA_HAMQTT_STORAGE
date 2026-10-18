#!/usr/bin/env bash
set -Eeuo pipefail

# Change this value when no version is supplied on the command line.
# Example published tags: 0.3.2, 0.3.3-rc1, latest
DEFAULT_VERSION="0.3.2"

readonly APP_SERVICES=(web mqtt-ingestor ha-ingestor cleanup mcp backup recovery)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE=(docker compose --project-name hamqtt-store -f "$ROOT/compose.yml" -f "$ROOT/compose.github.yml")
VERSION="$DEFAULT_VERSION"
VERSION_SET=false
DRY_RUN=false

log() {
    printf '\n[hamqtt-update] %s\n' "$*"
}

fail() {
    printf '\n[hamqtt-update] ERROR: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<EOF
Usage: ./update-from-github.sh [VERSION] [--dry-run]

Pull and deploy a version of HAMQTT from GitHub Container Registry.

Examples:
  ./update-from-github.sh
  ./update-from-github.sh 0.3.3
  ./update-from-github.sh 0.3.3-rc1 --dry-run

Default version: $DEFAULT_VERSION
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
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
            ;;
    esac
    shift
done

[[ "$VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] \
    || fail "Invalid image version '$VERSION'"
export HAMQTT_VERSION="$VERSION"

print_command() {
    printf '[hamqtt-update] +'
    printf ' %q' "$@"
    printf '\n'
}

run() {
    print_command "$@"
    if [[ "$DRY_RUN" != true ]]; then
        "$@"
    fi
}

compose() {
    run "${COMPOSE[@]}" "$@"
}

env_value() {
    local key="$1"
    if [[ -n "${!key:-}" ]]; then
        printf '%s' "${!key}"
    elif [[ -f "$ROOT/.env" ]]; then
        awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); sub(/[[:space:]]+#.*/, ""); gsub(/^"|"$/, ""); print; exit}' "$ROOT/.env"
    fi
}

container_exists() {
    docker container inspect "$1" >/dev/null 2>&1
}

container_image() {
    docker container inspect --format '{{.Config.Image}}' "$1"
}

container_is_hamqtt() {
    local name="$1"
    local label
    local image

    label="$(docker container inspect --format '{{index .Config.Labels "com.hamqtt.product"}}' "$name" 2>/dev/null || true)"
    [[ "$label" == "hamqtt-store" ]] && return 0

    image="$(container_image "$name")"
    case "$name" in
        "$POSTGRES_CONTAINER")
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

remove_remaining_containers() {
    local name
    for name in "${CONTAINERS[@]}"; do
        if container_exists "$name"; then
            container_is_hamqtt "$name" \
                || fail "Container '$name' changed ownership during update; refusing to remove it"
            log "Removing stale HAMQTT container $name"
            run docker rm -f "$name"
        fi
    done
}

ensure_network() {
    local network="$1"
    if ! docker network inspect "$network" >/dev/null 2>&1; then
        log "Creating external network $network"
        run docker network create --driver bridge "$network"
    fi
}

ensure_volume() {
    local volume="$1"
    if ! docker volume inspect "$volume" >/dev/null 2>&1; then
        log "Creating persistent volume $volume"
        run docker volume create "$volume"
    fi
}

wait_healthy() {
    local container="$1"
    local service="$2"
    local attempts="$3"
    local status
    local count

    if [[ "$DRY_RUN" == true ]]; then
        log "Would wait for $container to become healthy"
        return
    fi

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

    "${COMPOSE[@]}" logs --tail 100 "$service" || true
    fail "$container did not become healthy"
}

verify_web() {
    local count
    local health_url="http://127.0.0.1:${APP_PORT}/health"

    if [[ "$DRY_RUN" == true ]]; then
        log "Would verify $health_url"
        return
    fi

    for ((count = 1; count <= 30; count++)); do
        if command -v curl >/dev/null 2>&1 \
            && curl --fail --silent "$health_url" >/dev/null; then
            log "Web health check passed"
            return
        fi
        if ! command -v curl >/dev/null 2>&1 \
            && docker exec hamqtt-web python -c \
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()" \
                >/dev/null 2>&1; then
            log "Web health check passed"
            return
        fi
        sleep 2
    done

    "${COMPOSE[@]}" logs --tail 100 web || true
    fail "Web service did not become healthy at $health_url"
}

command -v docker >/dev/null 2>&1 || fail "Docker is not installed"
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is not available"
if [[ "$DRY_RUN" != true ]]; then
    docker info >/dev/null 2>&1 || fail "Docker daemon is not running or is not accessible"
fi
[[ -f "$ROOT/compose.yml" ]] || fail "Missing $ROOT/compose.yml"
[[ -f "$ROOT/compose.github.yml" ]] || fail "Missing $ROOT/compose.github.yml"
[[ -f "$ROOT/.env" ]] || fail "Missing $ROOT/.env; create it from .env.example and set secure values"

cd "$ROOT"

NETWORK="$(env_value POSTGRES_NETWORK)"
POSTGRES_VOLUME="$(env_value POSTGRES_VOLUME)"
APP_DATA_VOLUME="$(env_value APP_DATA_VOLUME)"
POSTGRES_CONTAINER="$(env_value POSTGRES_CONTAINER_NAME)"
APP_PORT="$(env_value APP_PORT)"
NETWORK="${NETWORK:-hamqtt-store-network}"
POSTGRES_VOLUME="${POSTGRES_VOLUME:-hamqtt-postgres-data}"
APP_DATA_VOLUME="${APP_DATA_VOLUME:-hamqtt-app-data}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-hamqtt-postgres}"
APP_PORT="${APP_PORT:-8000}"
readonly CONTAINERS=(
    "$POSTGRES_CONTAINER"
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

log "Selected HAMQTT version: $HAMQTT_VERSION"
[[ "$DRY_RUN" == true ]] && log "Dry-run mode: mutating commands will only be printed"

log "Validating Compose configuration"
"${COMPOSE[@]}" config --quiet

log "Current HAMQTT containers"
docker ps -a --filter 'name=^/hamqtt-' \
    --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' || true
check_container_ownership

log "Pulling version $HAMQTT_VERSION from GitHub Container Registry before downtime"
if [[ "$DRY_RUN" == true ]]; then
    compose pull
elif ! "${COMPOSE[@]}" pull; then
    fail "Image pull failed. Confirm that version '$HAMQTT_VERSION' is published. If the packages are private, run: docker login ghcr.io"
fi

log "Stopping and removing old HAMQTT containers without deleting volumes"
compose down --remove-orphans
remove_remaining_containers

ensure_network "$NETWORK"
ensure_volume "$POSTGRES_VOLUME"
ensure_volume "$APP_DATA_VOLUME"

log "Starting PostgreSQL and Redis"
compose up -d --no-deps postgres redis
wait_healthy "$POSTGRES_CONTAINER" postgres 90
wait_healthy hamqtt-redis redis 60

log "Applying database migrations; application services remain stopped until this succeeds"
compose run --rm --no-deps migrate

log "Starting HAMQTT application services"
compose up -d --no-deps "${APP_SERVICES[@]}"
verify_web

log "Update to version $HAMQTT_VERSION completed"
"${COMPOSE[@]}" ps -a
