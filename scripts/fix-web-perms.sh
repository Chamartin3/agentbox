#!/usr/bin/env bash
# Reset agentbox-web container + volumes so they run as the host user.
# Run from anywhere; needs sudo (for the one-time chown).
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

HOST_UID=$(id -u)
HOST_GID=$(id -g)
export UID=$HOST_UID GID=$HOST_GID 2>/dev/null || true

echo "→ chown host node_modules back to $USER ($HOST_UID:$HOST_GID)"
sudo chown -R "$HOST_UID:$HOST_GID" web/node_modules 2>/dev/null || true

echo "→ rebuild agentbox-web image with HOST_UID=$HOST_UID HOST_GID=$HOST_GID"
UID=$HOST_UID GID=$HOST_GID docker compose --profile dev build agentbox-web

echo "→ recreate the named node_modules volume"
UID=$HOST_UID GID=$HOST_GID docker compose --profile dev stop agentbox-web 2>/dev/null || true
UID=$HOST_UID GID=$HOST_GID docker compose --profile dev rm -f agentbox-web 2>/dev/null || true
docker volume rm "$(basename "$PWD")_agentbox-web-node-modules" 2>/dev/null || true

echo "→ start agentbox-web"
UID=$HOST_UID GID=$HOST_GID docker compose --profile dev up -d agentbox-web

echo "✓ done"
