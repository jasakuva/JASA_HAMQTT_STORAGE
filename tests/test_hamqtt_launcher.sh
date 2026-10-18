#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT

mkdir -p "$TEMP/podman" "$TEMP/docker"

cat >"$TEMP/podman/podman" <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == "container" && "$2" == "inspect" ]]; then exit 1; fi
if [[ "$1" == "network" && "$2" == "inspect" ]]; then exit 1; fi
if [[ "$1" == "volume" && "$2" == "inspect" ]]; then exit 1; fi
if [[ "$1" == "image" && "$2" == "inspect" && "${MOCK_MISSING_IMAGES:-false}" == "true" ]]; then exit 1; fi
printf 'mock podman:'
printf ' %q' "$@"
printf '\n'
EOF

cat >"$TEMP/podman/podman-compose" <<'EOF'
#!/usr/bin/env bash
printf 'mock podman-compose:'
printf ' %q' "$@"
printf '\n'
EOF

cat >"$TEMP/docker/docker" <<'EOF'
#!/usr/bin/env bash
if [[ "$1" == "container" && "$2" == "inspect" ]]; then exit 1; fi
if [[ "$1" == "network" && "$2" == "inspect" ]]; then exit 1; fi
if [[ "$1" == "volume" && "$2" == "inspect" ]]; then exit 1; fi
printf 'mock docker:'
printf ' %q' "$@"
printf '\n'
EOF

chmod +x "$TEMP/podman/podman" "$TEMP/podman/podman-compose" "$TEMP/docker/docker"

PATH="$TEMP/podman:/usr/bin:/bin" "$ROOT/hamqtt.sh" --engine podman --dry-run start >"$TEMP/podman-start"
if grep -q 'podman build' "$TEMP/podman-start"; then
    printf 'Start unexpectedly invoked a build\n' >&2
    exit 1
fi
if grep -q 'podman-compose down' "$TEMP/podman-start"; then
    printf 'Start unexpectedly recreated containers\n' >&2
    exit 1
fi
grep -q 'podman-compose up -d --no-deps postgres redis' "$TEMP/podman-start"

if MOCK_MISSING_IMAGES=true PATH="$TEMP/podman:/usr/bin:/bin" \
    "$ROOT/hamqtt.sh" --engine podman --dry-run start >"$TEMP/missing-start" 2>&1; then
    printf 'Start unexpectedly succeeded without required images\n' >&2
    exit 1
fi
grep -q 'Run ./hamqtt.sh update first' "$TEMP/missing-start"
if grep -q 'podman network create' "$TEMP/missing-start"; then
    printf 'Start created infrastructure before detecting missing images\n' >&2
    exit 1
fi

PATH="$TEMP/podman:/usr/bin:/bin" "$ROOT/hamqtt.sh" --engine podman --dry-run update >"$TEMP/podman-update"
grep -q 'podman build --pull=always' "$TEMP/podman-update"
grep -q 'podman-compose down' "$TEMP/podman-update"

PATH="$TEMP/podman:/usr/bin:/bin" "$ROOT/hamqtt.sh" --engine podman --dry-run rebuild >"$TEMP/podman-rebuild"
grep -q -- '--no-cache' "$TEMP/podman-rebuild"

PATH="$TEMP/podman:/usr/bin:/bin" "$ROOT/hamqtt.sh" --engine podman --dry-run stop >"$TEMP/podman-stop"
grep -q 'podman-compose stop' "$TEMP/podman-stop"

PATH="$TEMP/podman:/usr/bin:/bin" "$ROOT/hamqtt.sh" --engine podman --dry-run status >"$TEMP/podman-status"
grep -q 'podman-compose ps -a' "$TEMP/podman-status"

PATH="$TEMP/podman:/usr/bin:/bin" "$ROOT/hamqtt.sh" --engine podman --dry-run logs web >"$TEMP/podman-logs"
grep -q 'podman-compose logs --tail 100 web' "$TEMP/podman-logs"

PATH="$TEMP/docker:/usr/bin:/bin" "$ROOT/hamqtt.sh" --engine docker --dry-run update >"$TEMP/docker-update"
grep -q 'docker build --pull' "$TEMP/docker-update"
grep -q 'docker compose down' "$TEMP/docker-update"
grep -q 'docker compose up -d --no-deps postgres redis' "$TEMP/docker-update"
if grep -q -- '--pull=always' "$TEMP/docker-update"; then
    printf 'Docker command unexpectedly used Podman pull syntax\n' >&2
    exit 1
fi

PATH="$TEMP/podman:/usr/bin:/bin" "$ROOT/scripts/update.sh" --dry-run >"$TEMP/wrapper-update"
grep -q 'podman-compose down' "$TEMP/wrapper-update"

printf 'HAMQTT launcher validation passed\n'