#!/usr/bin/env bash
# The ONLY place that names specific backend CLIs — the Dockerfile stays
# backend-agnostic. Add/remove a line to change which backends ship in the
# image. Any failed install fails the build (pin or drop a package here if
# it goes missing upstream). Assumes NPM_CONFIG_PREFIX=/opt/npm-global.
set -euo pipefail

npm install -g @anthropic-ai/claude-code
npm install -g @openai/codex

# opencode-linux-x64 ships its binary one level deep in lib/ and skips the
# npm bin entry on purpose, so symlink it into bin/.
npm install -g opencode-linux-x64
ln -sf /opt/npm-global/lib/node_modules/opencode-linux-x64/bin/opencode \
       /opt/npm-global/bin/opencode

# pi-coding-agent bundles undici (needs Node 21+); skip its postinstall.
npm install -g --ignore-scripts @earendil-works/pi-coding-agent

chown -R appuser:appuser /opt/npm-global
