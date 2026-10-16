#!/usr/bin/env bash
set -Eeuo pipefail

# Backward-compatible update entry point. New usage: ./hamqtt.sh update
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/hamqtt.sh" "$@" update