#!/usr/bin/env bash
# Generic entrypoint: run any drop-in bootstrap scripts, then exec the CMD.
# Backend-specific setup (e.g. Claude credential merge) lives as a drop-in
# under /agentbox/entrypoint.d/ — baked in or mounted by compose, never here.
set -euo pipefail

if [[ -d /agentbox/entrypoint.d ]]; then
  for f in /agentbox/entrypoint.d/*.sh; do
    [[ -e "$f" ]] || continue   # no matches → glob stays literal
    bash "$f"
  done
fi

exec "$@"
