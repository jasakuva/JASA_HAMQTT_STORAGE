#!/usr/bin/env bash
set -Eeuo pipefail

readonly APP_SERVICES=(web mqtt-ingestor ha-ingestor mcp cleanup backup recovery)
readonly APP_CONTAINERS=(
    hamqtt-redis
    hamqtt-migrate
    hamqtt-web
    hamqtt-mqtt-ingestor
    hamqtt-ha-ingestor
    hamqtt-mcp
    hamqtt-cleanup
    hamqtt-backup
    hamqtt-recovery
)
ENGINE_REQUEST="${HAMQTT_ENGINE:-auto}"
DRY_RUN=false
ENGINE=""
COMPOSE=()

log() {
    printf '\n[hamqtt] %s\n' "$*"
}

fail() {
    printf '\n[hamqtt] ERROR: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Usage: ./hamqtt.sh [--engine podman|docker] [--dry-run] COMMAND [ARGUMENTS]

Commands:
  start              Start HAMQTT from existing local images without building
  stop               Stop containers without removing them or volumes
  update             Pull base images, rebuild, migrate, and recreate containers
  rebuild            Perform a no-cache rebuild, migrate, and recreate containers
  status             Show Compose service status
  logs [SERVICE]     Show the last 100 log lines, optionally for one service

Engine selection:
  Podman with podman-compose is preferred automatically. Docker Compose is used
  as a fallback. Set HAMQTT_ENGINE or pass --engine to select one explicitly.

Normal commands never delete named volumes. --dry-run prints mutating commands
without executing them.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --engine)
            [[ $# -ge 2 ]] || fail "--engine requires podman or docker"
            ENGINE_REQUEST="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            break
            ;;
    esac
done

COMMAND="${1:-}"
[[ -n "$COMMAND" ]] || { usage; exit 1; }
shift

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

podman_available() {
    command_exists podman && command_exists podman-compose && podman-compose version >/dev/null 2>&1
}

docker_available() {
    command_exists docker && docker compose version >/dev/null 2>&1
}

select_engine() {
    case "$ENGINE_REQUEST" in
        auto)
            if podman_available; then
                ENGINE="podman"
                COMPOSE=(podman-compose)
            elif docker_available; then
                ENGINE="docker"
                COMPOSE=(docker compose)
            else
                fail "Neither Podman with podman-compose nor Docker with Compose is available"
            fi
            ;;
        podman)
            podman_available || fail "Podman and podman-compose are required for --engine podman"
            ENGINE="podman"
            COMPOSE=(podman-compose)
            ;;
        docker)
            docker_available || fail "Docker with the Compose plugin is required for --engine docker"
            ENGINE="docker"
            COMPOSE=(docker compose)
            ;;
        *)
            fail "Unknown engine '$ENGINE_REQUEST'; choose podman or docker"
            ;;
    esac
}

print_command() {
    printf '[hamqtt] +'
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
    elif [[ -f .env ]]; then
        awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); sub(/[[:space:]]+#.*/, ""); gsub(/^\"|\"$/, ""); print; exit}' .env
    fi
}

container_exists() {
    "$ENGINE" container inspect "$1" >/dev/null 2>&1
}

container_image() {
    "$ENGINE" container inspect --format '{{.Config.Image}}' "$1"
}

container_is_owned() {
    local name="$1"
    local image
    local label
    image="$(container_image "$name")"
    label="$($ENGINE container inspect --format '{{index .Config.Labels "com.hamqtt.product"}}' "$name" 2>/dev/null || true)"

    if [[ "$label" == "hamqtt-store" ]]; then
        return 0
    fi
    case "$name" in
        hamqtt-postgres)
            [[ "$image" == localhost/hamqtt-postgres-pgbackrest:* || "$image" == *pgvector* ]]
            ;;
        hamqtt-redis)
            [[ "$image" == redis:* || "$image" == */redis:* ]]
            ;;
        hamqtt-backup|hamqtt-recovery)
            [[ "$image" == localhost/hamqtt-backup-pgbackrest:* ]]
            ;;
        *)
            [[ "$image" == localhost/hamqtt-store:* || "$image" == *hamqtt-store* ]]
            ;;
    esac
}

check_name_conflicts() {
    local name
    for name in "$POSTGRES_CONTAINER" "${APP_CONTAINERS[@]}"; do
        if container_exists "$name" && ! container_is_owned "$name"; then
            fail "Container '$name' exists but is not recognized as a HAMQTT container (image: $(container_image "$name")). Refusing to replace it."
        fi
    done
}

ensure_network() {
    if "$ENGINE" network inspect "$NETWORK" >/dev/null 2>&1; then
        return
    fi
    log "Creating network $NETWORK"
    run "$ENGINE" network create --driver bridge "$NETWORK"
}

ensure_volume() {
    local volume="$1"
    local description="$2"
    if "$ENGINE" volume inspect "$volume" >/dev/null 2>&1; then
        return
    fi
    log "Creating $description volume $volume"
    run "$ENGINE" volume create "$volume"
}

build_images() {
    local no_cache="${1:-false}"
    local pull_args=()
    local cache_args=()

    if [[ "$COMMAND" == "update" || "$COMMAND" == "rebuild" ]]; then
        if [[ "$ENGINE" == "podman" ]]; then
            pull_args=(--pull=always)
        else
            pull_args=(--pull)
        fi
    fi
    if [[ "$no_cache" == true ]]; then
        cache_args=(--no-cache)
    fi

    log "Building application image"
    run "$ENGINE" build "${pull_args[@]}" "${cache_args[@]}" -f build/Dockerfile -t localhost/hamqtt-store:dev .
    log "Building PostgreSQL image"
    run "$ENGINE" build "${pull_args[@]}" "${cache_args[@]}" -f build/PostgresBackupDockerfile -t localhost/hamqtt-postgres-pgbackrest:dev .
    log "Building backup and recovery image"
    run "$ENGINE" build "${pull_args[@]}" "${cache_args[@]}" -f build/BackupDockerfile -t localhost/hamqtt-backup-pgbackrest:dev .
}

require_local_images() {
    local image
    local missing=false
    local images=(
        localhost/hamqtt-store:dev
        localhost/hamqtt-postgres-pgbackrest:dev
        localhost/hamqtt-backup-pgbackrest:dev
    )

    for image in "${images[@]}"; do
        if ! "$ENGINE" image inspect "$image" >/dev/null 2>&1; then
            printf 'Missing required local image: %s\n' "$image" >&2
            missing=true
        fi
    done
    if [[ "$missing" == true ]]; then
        fail "Run ./hamqtt.sh update first to build the required images"
    fi
}

wait_healthy() {
    local container="$1"
    local attempts="$2"
    local service="$3"
    local status
    local count

    if [[ "$DRY_RUN" == true ]]; then
        log "Would wait for $container to become healthy"
        return
    fi
    for ((count = 1; count <= attempts; count++)); do
        status="$($ENGINE container inspect --format '{{.State.Health.Status}}' "$container" 2>/dev/null || true)"
        if [[ "$status" == "healthy" ]]; then
            log "$container is healthy"
            return
        fi
        sleep 2
    done
    compose logs --tail 100 "$service" || true
    fail "$container did not become healthy"
}

verify_web() {
    local count
    if [[ "$DRY_RUN" == true ]]; then
        log "Would verify http://localhost:8000/health"
        return
    fi
    for ((count = 1; count <= 30; count++)); do
        if command_exists curl && curl --fail --silent http://localhost:8000/health >/dev/null 2>&1; then
            log "Web health check passed"
            return
        fi
        if ! command_exists curl && command_exists wget && wget -q --spider http://localhost:8000/health >/dev/null 2>&1; then
            log "Web health check passed"
            return
        fi
        if ! command_exists curl && ! command_exists wget \
            && "$ENGINE" exec hamqtt-web python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()" >/dev/null 2>&1; then
            log "Web health check passed"
            return
        fi
        sleep 2
    done
    compose logs --tail 100 web || true
    fail "Web service did not become healthy at http://localhost:8000/health"
}

prepare_infrastructure() {
    check_name_conflicts
    ensure_network
    ensure_volume "$POSTGRES_VOLUME" "persistent database"
    ensure_volume "$APP_DATA_VOLUME" "persistent application-data"
}

start_stack() {
    local build="${1:-false}"
    local recreate="${2:-false}"
    local no_cache="${3:-false}"

    if [[ "$build" == true ]]; then
        prepare_infrastructure
        build_images "$no_cache"
    else
        require_local_images
        prepare_infrastructure
    fi

    if [[ "$recreate" == true ]]; then
        log "Recreating containers without deleting named volumes"
        compose down
    fi

    log "Starting PostgreSQL and Redis"
    compose up -d --no-deps postgres redis
    wait_healthy "$POSTGRES_CONTAINER" 90 postgres
    wait_healthy hamqtt-redis 60 redis

    log "Applying database migrations"
    compose run --rm --no-deps migrate

    log "Starting application services"
    compose up -d --no-deps "${APP_SERVICES[@]}"
    verify_web
    compose ps -a
}

select_engine
cd "$(dirname "${BASH_SOURCE[0]}")"
[[ -f compose.yml ]] || fail "hamqtt.sh must be located beside compose.yml"

NETWORK_VALUE="$(env_value POSTGRES_NETWORK)"
POSTGRES_VOLUME_VALUE="$(env_value POSTGRES_VOLUME)"
APP_DATA_VOLUME_VALUE="$(env_value APP_DATA_VOLUME)"
POSTGRES_CONTAINER_VALUE="$(env_value POSTGRES_CONTAINER_NAME)"
readonly NETWORK="${NETWORK_VALUE:-hamqtt-store-network}"
readonly POSTGRES_VOLUME="${POSTGRES_VOLUME_VALUE:-hamqtt-postgres-data}"
readonly APP_DATA_VOLUME="${APP_DATA_VOLUME_VALUE:-hamqtt-app-data}"
readonly POSTGRES_CONTAINER="${POSTGRES_CONTAINER_VALUE:-hamqtt-postgres}"

log "Using $ENGINE with ${COMPOSE[*]}"
[[ "$DRY_RUN" == true ]] && log "Dry-run mode: mutating commands will only be printed"

case "$COMMAND" in
    start)
        [[ $# -eq 0 ]] || fail "start does not accept arguments"
        start_stack false false false
        ;;
    stop)
        [[ $# -eq 0 ]] || fail "stop does not accept arguments"
        compose stop
        compose ps -a
        ;;
    update)
        [[ $# -eq 0 ]] || fail "update does not accept arguments"
        start_stack true true false
        ;;
    rebuild)
        [[ $# -eq 0 ]] || fail "rebuild does not accept arguments"
        start_stack true true true
        ;;
    status)
        [[ $# -eq 0 ]] || fail "status does not accept arguments"
        compose ps -a
        ;;
    logs)
        [[ $# -le 1 ]] || fail "logs accepts at most one service name"
        if [[ $# -eq 1 ]]; then
            compose logs --tail 100 "$1"
        else
            compose logs --tail 100
        fi
        ;;
    *)
        usage
        fail "Unknown command '$COMMAND'"
        ;;
esac