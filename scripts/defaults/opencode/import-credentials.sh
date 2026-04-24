#!/usr/bin/env bash
# One-shot: import OpenCode credentials from the host machine into the
# agentbox-opencode named volume so the containerized OpenCode starts
# authenticated.
#
# Run once after first bringing the agentbox stack up. The volume persists
# auth tokens across container recreations.
#
# Usage:
#   scripts/defaults/opencode/import-credentials.sh                          # uses default path
#   scripts/defaults/opencode/import-credentials.sh /path/to/opencode/dir
#
# Env:
#   AGENTBOX_OPENCODE_VOLUME   docker volume name (default: auto-detected)
set -euo pipefail

HOST_OPENCODE_DIR="${1:-$HOME/.local/share/opencode}"
VOLUME="${AGENTBOX_OPENCODE_VOLUME:-}"

if [[ ! -f "$HOST_OPENCODE_DIR/auth.json" ]]; then
  echo "No auth.json found at $HOST_OPENCODE_DIR/auth.json" >&2
  echo "Run \`opencode\` on the host and complete authentication first," >&2
  echo "or pass a different path as the first argument." >&2
  exit 1
fi

if [[ -z "$VOLUME" ]]; then
  VOLUME=$(docker volume ls --format '{{.Name}}' | grep -E '_agentbox-opencode$' | head -n 1 || true)
  if [[ -z "$VOLUME" ]]; then
    echo "Couldn't find an agentbox-opencode volume. Bring the stack up first," >&2
    echo "or set AGENTBOX_OPENCODE_VOLUME explicitly." >&2
    echo "" >&2
    echo "Note: the agentbox-opencode volume is optional — add it to your" >&2
    echo "docker-compose.override.yml to enable OpenCode auth persistence." >&2
    exit 1
  fi
fi

UID_GID="${UID:-1000}:${GID:-1000}"

docker run --rm \
  -v "$HOST_OPENCODE_DIR:/host:ro" \
  -v "$VOLUME:/dst" \
  alpine sh -c "mkdir -p /dst \
    && cp /host/auth.json /dst/auth.json \
    && chown ${UID_GID} /dst/auth.json \
    && chmod 600 /dst/auth.json"

echo "Imported credentials from $HOST_OPENCODE_DIR into volume $VOLUME."
echo "OpenCode should now start authenticated inside the agentbox container."
