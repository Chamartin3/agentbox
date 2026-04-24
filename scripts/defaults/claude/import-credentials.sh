#!/usr/bin/env bash
# One-shot: import Claude Code credentials from the host machine into the
# agentbox-claude named volume so the containerized Claude starts authenticated.
#
# Run once after first bringing the agentbox stack up. The volume persists
# OAuth tokens across container recreations.
#
# Usage:
#   scripts/defaults/claude/import-credentials.sh             # uses $HOME/.claude
#   scripts/defaults/claude/import-credentials.sh /path/.claude
#
# Env:
#   AGENTBOX_CLAUDE_VOLUME   docker volume name (default: auto-detected)
set -euo pipefail

HOST_CLAUDE_DIR="${1:-$HOME/.claude}"
VOLUME="${AGENTBOX_CLAUDE_VOLUME:-}"

if [[ ! -f "$HOST_CLAUDE_DIR/.credentials.json" ]]; then
  echo "No .credentials.json found at $HOST_CLAUDE_DIR/.credentials.json" >&2
  echo "Run \`claude /login\` on the host first, or pass a different path." >&2
  exit 1
fi

if [[ -z "$VOLUME" ]]; then
  VOLUME=$(docker volume ls --format '{{.Name}}' | grep -E '_agentbox-claude$' | head -n 1 || true)
  if [[ -z "$VOLUME" ]]; then
    echo "Couldn't find an agentbox-claude volume. Bring the stack up first," >&2
    echo "or set AGENTBOX_CLAUDE_VOLUME explicitly." >&2
    exit 1
  fi
fi

UID_GID="${UID:-1000}:${GID:-1000}"

docker run --rm \
  -v "$HOST_CLAUDE_DIR:/host:ro" \
  -v "$VOLUME:/dst" \
  alpine sh -c "cp /host/.credentials.json /dst/.credentials.json \
    && chown ${UID_GID} /dst/.credentials.json \
    && chmod 600 /dst/.credentials.json"

echo "Imported credentials from $HOST_CLAUDE_DIR into volume $VOLUME."
echo "Claude should now start authenticated inside the agentbox container."
