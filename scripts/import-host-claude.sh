#!/usr/bin/env bash
# Import host Claude credentials into an agentbox named volume.
#
# Usage:
#   scripts/import-host-claude.sh [source-dir] [profile-name]
#
#   source-dir     Host path to ~/.claude to copy from (default: ~/.claude)
#   profile-name   Optional creds profile suffix (e.g. "drafting" → volume
#                  agentbox-claude-drafting). When omitted, writes to the
#                  default agentbox-claude volume.
#
# Examples:
#   scripts/import-host-claude.sh ~/.claude              # → agentbox-claude
#   scripts/import-host-claude.sh ~/.claude drafting     # → agentbox-claude-drafting
#   scripts/import-host-claude.sh ~/.claude-dotty research  # → agentbox-claude-research
#
# Environment:
#   AGENTBOX_CONTAINER   Container name (default: cvagents-agentbox)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTBOX_CONTAINER="${AGENTBOX_CONTAINER:-cvagents-agentbox}"

SRC_DIR="${1:-$HOME/.claude}"
PROFILE="${2:-}"

if [[ -n "$PROFILE" ]]; then
  VOLUME="agentbox-claude-${PROFILE}"
  TARGET="/agentbox/creds/claude-${PROFILE}"
else
  VOLUME="agentbox-claude"
  TARGET="/agentbox/creds/claude"
fi

if [[ ! -f "$SRC_DIR/credentials.json" ]] && [[ ! -f "$SRC_DIR/.credentials.json" ]]; then
  echo "ERROR: no credentials found in $SRC_DIR" >&2
  echo "Authenticate first with: claude /login" >&2
  exit 1
fi

echo "Importing credentials from $SRC_DIR → volume $VOLUME ($TARGET)..."

# Copy credentials into the container at the target path. Docker named volumes
# are owned by the container's user (UID 1000), so we write through the
# running container rather than manipulating the volume directly.
docker cp "$SRC_DIR/credentials.json" "${AGENTBOX_CONTAINER}:${TARGET}/credentials.json" 2>/dev/null \
  || docker cp "$SRC_DIR/.credentials.json" "${AGENTBOX_CONTAINER}:${TARGET}/.credentials.json" 2>/dev/null \
  || { echo "ERROR: failed to copy credentials — is $AGENTBOX_CONTAINER running?" >&2; exit 1; }

echo "Done. Authenticate with a fresh login if needed:"
echo "  docker exec -e CLAUDE_CONFIG_DIR=${TARGET} -it ${AGENTBOX_CONTAINER} claude /login"
