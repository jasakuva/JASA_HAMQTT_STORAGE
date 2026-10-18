#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMP="$(mktemp -d)"
trap 'rm -rf "$TEMP"' EXIT

mkdir -p "$TEMP/bin"
cp "$ROOT/deploy/install.sh" "$TEMP/install.sh"

cat >"$TEMP/bin/docker" <<'EOF'
#!/usr/bin/env bash
printf 'docker' >>"$MOCK_DOCKER_LOG"
printf ' %q' "$@" >>"$MOCK_DOCKER_LOG"
printf '\n' >>"$MOCK_DOCKER_LOG"

if [[ "$1" == "compose" && "$2" == "version" ]]; then
    exit 0
fi
if [[ "$1" == "info" ]]; then
    exit 0
fi
if [[ "$1" == "container" && "$2" == "inspect" ]]; then
    if [[ " $* " == *" --format "* && "$*" == *".State.Health.Status"* ]]; then
        printf 'healthy\n'
        exit 0
    fi
    if [[ " $* " == *" --format "* && "$*" == *".Config.User"* ]]; then
        printf '999:999\n'
        exit 0
    fi
    exit 1
fi
if [[ "$1" == "network" && "$2" == "inspect" ]]; then
    exit 1
fi
if [[ "$1" == "volume" && "$2" == "inspect" ]]; then
    exit 1
fi
exit 0
EOF

cat >"$TEMP/bin/curl" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

cat >"$TEMP/bin/sudo" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "-v" ]]; then
    exit 0
fi
exec "$@"
EOF

cat >"$TEMP/bin/chown" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

chmod +x "$TEMP/bin/docker" "$TEMP/bin/curl" "$TEMP/bin/sudo" "$TEMP/bin/chown"

run_install() {
    local work="$1"
    shift
    mkdir -p "$work"
    : >"$work/docker.log"
    (
        cd "$work"
        PATH="$TEMP/bin:/usr/bin:/bin" MOCK_DOCKER_LOG="$work/docker.log" \
            bash "$TEMP/install.sh" "$@" >"$work/output" 2>&1
    )
}

run_install "$TEMP/default"
DEFAULT_INSTALL="$TEMP/default/jasa_hamqtt_storage"
grep -q '^HAMQTT_VERSION=latest$' "$DEFAULT_INSTALL/.env"
grep -q '^POSTGRES_PASSWORD=[0-9a-f]\{48\}$' "$DEFAULT_INSTALL/.env"
grep -q '^SECRET_KEY=[0-9a-f]\{64\}$' "$DEFAULT_INSTALL/.env"
[[ "$(stat -c '%a' "$DEFAULT_INSTALL/.env")" == "600" ]]
[[ -f "$DEFAULT_INSTALL/compose.yml" ]]
[[ -f "$DEFAULT_INSTALL/pgbackrest.conf" ]]
[[ -f "$DEFAULT_INSTALL/db/init/001-enable-extensions.sql" ]]
[[ -d "$DEFAULT_INSTALL/backups" ]]
grep -q 'ghcr.io/jasakuva/hamqtt-store:${HAMQTT_VERSION:-latest}' "$DEFAULT_INSTALL/compose.yml"
grep -q 'user: "999:999"' "$DEFAULT_INSTALL/compose.yml"
grep -q 'compose.*pull' "$TEMP/default/docker.log"
grep -q 'up -d --no-deps postgres redis' "$TEMP/default/docker.log"
grep -q 'pgbackrest.*stanza-create' "$TEMP/default/docker.log"
grep -q 'pgbackrest.*check' "$TEMP/default/docker.log"
grep -q 'run --rm --no-deps migrate' "$TEMP/default/docker.log"
grep -q 'up -d --no-deps web mqtt-ingestor ha-ingestor cleanup mcp backup recovery' "$TEMP/default/docker.log"

password="$(sed -n 's/^POSTGRES_PASSWORD=//p' "$DEFAULT_INSTALL/.env")"
secret="$(sed -n 's/^SECRET_KEY=//p' "$DEFAULT_INSTALL/.env")"
if grep -Fq "$password" "$TEMP/default/output" || grep -Fq "$secret" "$TEMP/default/output"; then
    printf 'Installer printed a generated secret\n' >&2
    exit 1
fi

if grep -Eq 'down -v|volume rm' "$TEMP/default/docker.log"; then
    printf 'Installer attempted to delete persistent data\n' >&2
    exit 1
fi

run_install "$TEMP/versioned" --version 0.3.3-rc2
grep -q '^HAMQTT_VERSION=0.3.3-rc2$' "$TEMP/versioned/jasa_hamqtt_storage/.env"

run_install "$TEMP/positional" 9.8.7
grep -q '^HAMQTT_VERSION=9.8.7$' "$TEMP/positional/jasa_hamqtt_storage/.env"

mkdir -p "$TEMP/existing/jasa_hamqtt_storage"
: >"$TEMP/existing/docker.log"
if (
    cd "$TEMP/existing"
    PATH="$TEMP/bin:/usr/bin:/bin" MOCK_DOCKER_LOG="$TEMP/existing/docker.log" \
        bash "$TEMP/install.sh" >"$TEMP/existing/output" 2>&1
); then
    printf 'Installer accepted an existing installation directory\n' >&2
    exit 1
fi
[[ ! -s "$TEMP/existing/docker.log" ]]
grep -q 'already exists' "$TEMP/existing/output"

mkdir -p "$TEMP/invalid"
: >"$TEMP/invalid/docker.log"
if (
    cd "$TEMP/invalid"
    PATH="$TEMP/bin:/usr/bin:/bin" MOCK_DOCKER_LOG="$TEMP/invalid/docker.log" \
        bash "$TEMP/install.sh" 'bad/version' >"$TEMP/invalid/output" 2>&1
); then
    printf 'Installer accepted an invalid image tag\n' >&2
    exit 1
fi
[[ ! -e "$TEMP/invalid/jasa_hamqtt_storage" ]]
[[ ! -s "$TEMP/invalid/docker.log" ]]

printf 'Linux installer validation passed\n'