#!/usr/bin/env bash
set -Eeuo pipefail

# Consumer-safe HAMQTT update/bootstrap command.
# Usage: bash scripts/update.sh

readonly APP_SERVICES=(web mqtt-ingestor ha-ingestor mcp)
readonly APP_CONTAINERS=(hamqtt-web hamqtt-mqtt-ingestor hamqtt-ha-ingestor hamqtt-mcp)
readonly PRODUCT_LABEL="com.hamqtt.product=hamqtt-store"

log() {
    printf '\n[hamqtt] %s\n' "$*"
}

fail() {
    printf '\n[hamqtt] ERROR: %s\n' "$*" >&2
    exit 1
}

command -v bash >/dev/null 2>&1 || fail "bash is required"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    readonly ENGINE=docker
    compose() { docker compose "$@"; }
elif command -v podman >/dev/null 2>&1 && podman compose version >/dev/null 2>&1; then
    readonly ENGINE=podman
    compose() { podman compose "$@"; }
else
    fail "Docker Compose or Podman Compose is required"
fi

env_value() {
    local key="$1"
    if [[ -n "${!key:-}" ]]; then
        printf '%s' "${!key}"
    elif [[ -f .env ]]; then
        awk -F= -v key="$key" '$1 == key {sub(/^[^=]*=/, ""); sub(/[[:space:]]+#.*/, ""); gsub(/^\"|\"$/, ""); print; exit}' .env
    fi
}

readonly NETWORK_NAME="$(env_value POSTGRES_NETWORK)"
readonly VOLUME_NAME="$(env_value POSTGRES_VOLUME)"
readonly POSTGRES_CONTAINER="$(env_value POSTGRES_CONTAINER_NAME)"
readonly NETWORK="${NETWORK_NAME:-hamqtt-store-network}"
readonly VOLUME="${VOLUME_NAME:-hamqtt-postgres-data}"
readonly POSTGRES="${POSTGRES_CONTAINER:-hamqtt-postgres}"

container_exists() {
    "$ENGINE" container inspect "$1" >/dev/null 2>&1
}

container_image() {
    "$ENGINE" container inspect --format '{{.Config.Image}}' "$1"
}

container_is_owned() {
    local name="$1"
    local role="$2"
    local image
    local label
    image="$(container_image "$name")"
    label="$($ENGINE container inspect --format '{{index .Config.Labels "com.hamqtt.product"}}' "$name" 2>/dev/null || true)"

    if [[ "$label" == "hamqtt-store" || "$image" == localhost/hamqtt-store:* || "$image" == *hamqtt-store* ]]; then
        return 0
    fi
    if [[ "$role" == "postgres" && "$image" == *pgvector* ]]; then
        return 0
    fi
    return 1
}

check_name_conflict() {
    local name="$1"
    local role="$2"
    if ! container_exists "$name"; then
        return
    fi
    if container_is_owned "$name" "$role"; then
        return
    fi
    fail "Container '$name' already exists but is not recognized as a HAMQTT container (image: $(container_image "$name")). Refusing to remove it. Stop or rename that container, then retry."
}

ensure_network() {
    if "$ENGINE" network inspect "$NETWORK" >/dev/null 2>&1; then
        return
    fi
    log "Creating network $NETWORK"
    "$ENGINE" network create --driver bridge "$NETWORK" >/dev/null
}

ensure_volume() {
    if "$ENGINE" volume inspect "$VOLUME" >/dev/null 2>&1; then
        return
    fi
    log "Creating persistent database volume $VOLUME"
    "$ENGINE" volume create "$VOLUME" >/dev/null
}

wait_for_postgres() {
    local status
    for _ in $(seq 1 60); do
        if container_exists "$POSTGRES"; then
            status="$($ENGINE container inspect --format '{{.State.Health.Status}}' "$POSTGRES" 2>/dev/null || true)"
            if [[ "$status" == "healthy" ]]; then
                return
            fi
        fi
        sleep 2
    done
    compose logs --tail 100 postgres || true
    fail "PostgreSQL did not become healthy"
}

remove_owned_container() {
    local name="$1"
    if container_exists "$name"; then
        log "Replacing $name"
        "$ENGINE" rm -f "$name" >/dev/null
    fi
}

cd "$(dirname "${BASH_SOURCE[0]}")/.."

[[ -f compose.yml ]] || fail "Run this script from a HAMQTT checkout containing compose.yml"

log "Using $ENGINE Compose"
ensure_network
ensure_volume

check_name_conflict "$POSTGRES" "postgres"
for container in "${APP_CONTAINERS[@]}"; do
    check_name_conflict "$container" "application"
done

log "Building application image"
compose build

log "Starting PostgreSQL"
if container_exists "$POSTGRES"; then
    postgres_status="$($ENGINE container inspect --format '{{.State.Status}}' "$POSTGRES")"
    if [[ "$postgres_status" != "running" ]]; then
        "$ENGINE" start "$POSTGRES" >/dev/null
    fi
else
    compose up -d --no-deps postgres
fi
wait_for_postgres

log "Applying database migrations"
compose run --rm --no-deps migrate

for container in "${APP_CONTAINERS[@]}"; do
    remove_owned_container "$container"
done

log "Starting updated application services"
compose up -d --no-deps "${APP_SERVICES[@]}"

log "Waiting for the web service"
for _ in $(seq 1 30); do
    if command -v curl >/dev/null 2>&1 && curl --fail --silent http://localhost:8000/health >/dev/null 2>&1; then
        log "Update completed successfully"
        compose ps
        exit 0
    fi
    sleep 2
done

compose ps
compose logs --tail 100 web || true
fail "Web service did not become healthy at http://localhost:8000/health"