#!/usr/bin/env bash
# THROWAWAY — safe to delete after the agentbox image is rebuilt.
# Rebuilds the agentbox docker image so Python + SPA changes in
# libs/agentbox/ take effect in the running container.
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")/.."   # → cv_agents root

HOST_UID=$(id -u)
HOST_GID=$(id -g)

echo "→ rebuilding cvagents-agentbox image (no cache, multi-stage: vite build + python install)"
env UID="$HOST_UID" GID="$HOST_GID" docker compose build --no-cache agentbox

echo "→ recreating container"
env UID="$HOST_UID" GID="$HOST_GID" docker compose up -d --force-recreate --no-deps agentbox

echo "✓ done. Hard-refresh http://localhost:8765/ (Ctrl-Shift-R)"
