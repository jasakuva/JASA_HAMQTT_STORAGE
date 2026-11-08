#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT

mkdir -p "$TEMP/deploy" "$TEMP/bin"
cp "$ROOT/deploy/update-from-github.sh" "$ROOT/compose.yml" "$ROOT/pgbackrest.conf" "$TEMP/deploy/"
cp -R "$ROOT/db" "$TEMP/deploy/db"
cp "$ROOT/.env.example" "$TEMP/deploy/.env"

cat >"$TEMP/bin/docker" <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == "compose" && "$2" == "version" && "${MOCK_COMPOSE_V2:-true}" == "true" ]]; then
    exit 0
fi
if [[ "$1" == "compose" && "$2" == "version" ]]; then
    exit 1
fi
if [[ "$1" == "compose" && " $* " == *" config --quiet "* ]]; then
    exit 0
fi
if [[ "$1" == "container" && "$2" == "inspect" ]]; then
    exit 1
fi
if [[ "$1" == "network" && "$2" == "inspect" ]]; then
    exit 1
fi
if [[ "$1" == "volume" && "$2" == "inspect" ]]; then
    exit 1
fi
printf 'mock docker:'
printf ' %q' "$@"
printf '\n'
EOF
cat >"$TEMP/bin/docker-compose" <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == "version" ]]; then
    exit 0
fi
printf 'mock docker-compose:'
printf ' %q' "$@"
printf '\n'
EOF
chmod +x "$TEMP/bin/docker" "$TEMP/bin/docker-compose" "$TEMP/deploy/update-from-github.sh"

PATH="$TEMP/bin:/usr/bin:/bin" \
    "$TEMP/deploy/update-from-github.sh" 9.8.7 --dry-run >"$TEMP/output"

grep -q 'Selected HAMQTT version: 9.8.7' "$TEMP/output"
grep -q 'compose.yml.*pull' "$TEMP/output"
grep -q 'compose.yml.*down --remove-orphans' "$TEMP/output"
grep -q 'docker network create --driver bridge hamqtt-store-network' "$TEMP/output"
grep -q 'docker volume create hamqtt-postgres-data' "$TEMP/output"
grep -q 'docker volume create hamqtt-app-data' "$TEMP/output"
grep -q 'up -d --no-deps postgres redis' "$TEMP/output"
grep -q 'run --rm --no-deps migrate' "$TEMP/output"
grep -q 'up -d --no-deps web mqtt-ingestor ha-ingestor cleanup mcp backup recovery' "$TEMP/output"
grep -q 'persist_version' "$ROOT/deploy/update-from-github.sh"
grep -q 'HAMQTT_VERSION=' "$ROOT/deploy/update-from-github.sh"

if grep -Eq 'down -v|volume rm' "$TEMP/output"; then
    printf 'Updater attempted to delete persistent volumes\n' >&2
    exit 1
fi

PATH="$TEMP/bin:/usr/bin:/bin" MOCK_COMPOSE_V2=false \
    "$TEMP/deploy/update-from-github.sh" 9.8.7 --dry-run >"$TEMP/legacy-output"
grep -q 'docker-compose.*compose.yml.*pull' "$TEMP/legacy-output"

if PATH="$TEMP/bin:/usr/bin:/bin" \
    "$TEMP/deploy/update-from-github.sh" 1.0.0 2.0.0 --dry-run >/dev/null 2>&1; then
    printf 'Updater accepted multiple versions\n' >&2
    exit 1
fi

if PATH="$TEMP/bin:/usr/bin:/bin" \
    "$TEMP/deploy/update-from-github.sh" 'bad/version' --dry-run >/dev/null 2>&1; then
    printf 'Updater accepted an invalid image tag\n' >&2
    exit 1
fi

printf 'GitHub image updater validation passed\n'