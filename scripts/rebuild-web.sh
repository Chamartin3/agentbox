#!/usr/bin/env bash
# DEPRECATED — use `./dev.sh rebuild-web` from libs/agentbox/ instead.
# This thin wrapper exists only so existing muscle memory keeps working.
set -euo pipefail
exec "$(dirname "$(readlink -f "$0")")/../dev.sh" rebuild-web
