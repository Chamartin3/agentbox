#!/usr/bin/env bash
# migrate-host-layout.sh — migrate from the legacy Project-root mount to the
# Plan-08 manifest-only host contract.
#
# Usage: bash libs/agentbox/scripts/migrate-host-layout.sh
#
# The script is safe to re-run; it prints instructions and runs
# `agentbox migrate workspace-permissions` inside the container.

set -euo pipefail

RED='\033[0;31m'
YEL='\033[1;33m'
GRN='\033[0;32m'
BLD='\033[1m'
RST='\033[0m'

CONTAINER="${AGENTBOX_CONTAINER_NAME:-agentbox}"

hr() { printf '%0.s─' {1..60}; echo; }

hr
echo -e "${BLD}agentbox host layout migration${RST} (legacy → v1.0.0)"
hr

# ── Check container image ─────────────────────────────────────────────────────

if docker inspect "$CONTAINER" &>/dev/null; then
    LAYOUT=$(docker exec "$CONTAINER" cat /agentbox/.layout-v2 2>/dev/null || true)
    if [[ -z "$LAYOUT" ]]; then
        echo -e "${RED}✗  Container '$CONTAINER' is running the OLD image (no /agentbox/.layout-v2).${RST}"
        echo "   Rebuild your image and bring it up with the new compose file first."
        exit 1
    fi
    echo -e "${GRN}✓  Container '$CONTAINER' is running a v2-compatible image.${RST}"
else
    echo -e "${YEL}⚠  Container '$CONTAINER' is not running — skipping image check.${RST}"
fi

# ── Step 1: migrate workspace permissions ─────────────────────────────────────

echo
echo -e "${BLD}Step 1:${RST} migrate capabilities.json → manifest workspace blocks"
if docker inspect "$CONTAINER" &>/dev/null; then
    docker exec "$CONTAINER" agentbox migrate workspace-permissions && \
        echo -e "${GRN}✓  Done.${RST}" || \
        echo -e "${YEL}⚠  Migration returned non-zero (check output above).${RST}"
else
    echo "   Container not running — run this manually after starting the container:"
    echo "   docker exec \$CONTAINER agentbox migrate workspace-permissions"
fi

# ── Step 2: new compose snippet ───────────────────────────────────────────────

echo
hr
echo -e "${BLD}Step 2:${RST} update your project's .env"
echo
cat <<'ENV'
# Add these to your .env (remove AGENTBOX_PROJECT_DIR):
AGENTBOX_MANIFEST=./agentbox.toml

# Optional — omit or set to /dev/null to skip:
# AGENTBOX_AGENTS_DIR=./agents.d
# AGENTBOX_PROMPTS_DIR=./prompts
# AGENTBOX_SKILLS_DIR=./skills
# AGENTBOX_OUTPUTS_DIR=./outputs
ENV

# ── Step 3: files to delete from the consumer repo ───────────────────────────

echo
hr
echo -e "${BLD}Step 3:${RST} files safe to delete from the consumer repo"
echo
CANDIDATES=(
    "bin/agentbox_sync.py"
    "bin/generate_configs.py"
    "bin/_generated"
    "agentbox"
)
for f in "${CANDIDATES[@]}"; do
    if [[ -e "$f" ]]; then
        echo -e "  ${RED}DELETE${RST}  $f"
    else
        echo -e "  ${GRN}OK${RST}      $f (already gone)"
    fi
done
echo
echo "Remove the ones marked DELETE, then verify your stack still starts."
hr
echo -e "${GRN}Migration checklist complete.${RST}"
