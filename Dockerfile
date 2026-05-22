# Multi-stage: build the React SPA, then assemble the Python runtime.

FROM node:20-alpine AS web
WORKDIR /web
COPY libs/agentbox/web/package.json ./
RUN npm install --no-audit --no-fund
COPY libs/agentbox/web/ ./
# Vite builds into /opt/agentbox/src/agentbox/ui/static/dist via vite.config.ts;
# we redirect the output here instead.
RUN npx vite build --outDir /web/dist

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
ENV AGENTBOX_DATA_DIR=/data AGENTBOX_PROJECT_ROOT=/project AGENTBOX_PORT=8765

ARG UID=1000
ARG GID=1000
RUN groupadd -g ${GID} appuser \
 && useradd -m -u ${UID} -g ${GID} -s /bin/bash appuser

# Base tools. Node is installed separately from NodeSource because the
# pi-coding-agent CLI bundles undici, which requires Node 21+ APIs
# (markAsUncloneable) that Debian's default Node 20 LTS lacks.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates git jq tini unzip vim \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && curl -LO https://github.com/sxyazi/yazi/releases/download/v26.5.6/yazi-x86_64-unknown-linux-gnu.deb \
    && dpkg -i yazi-x86_64-unknown-linux-gnu.deb || apt-get install -f -y \
    && rm -f yazi-x86_64-unknown-linux-gnu.deb \
    && rm -rf /var/lib/apt/lists/*

ENV NPM_CONFIG_PREFIX=/opt/npm-global
ENV PATH=/opt/npm-global/bin:$PATH
RUN mkdir -p /opt/npm-global \
 && chown -R appuser:appuser /opt/npm-global

# Backend CLIs — installed at build time so they're part of the image
# layer (not the runtime volume). Failure of any one install fails the
# build; if a package becomes unavailable upstream, pin or drop it here.
# opencode-linux-x64 ships the binary one level deep in lib/, so we
# symlink it into bin/ (its npm package skips the bin entry on purpose).
RUN npm install -g @anthropic-ai/claude-code \
 && npm install -g opencode-linux-x64 \
 && ln -sf /opt/npm-global/lib/node_modules/opencode-linux-x64/bin/opencode \
           /opt/npm-global/bin/opencode \
 && npm install -g @openai/codex \
 && npm install -g --ignore-scripts @earendil-works/pi-coding-agent \
 && chown -R appuser:appuser /opt/npm-global

WORKDIR /opt/agentbox
COPY libs/agentbox/pyproject.toml ./
COPY libs/agentbox/src ./src
COPY libs/agentbox/alembic ./alembic
COPY libs/agentbox/alembic.ini ./alembic.ini

# Drop the SPA into the place FastAPI expects.
COPY --from=web /web/dist /opt/agentbox/src/agentbox/ui/static/dist

RUN pip install --no-cache-dir -e . websockets

# Legacy consumer plugins (entry-point plugins resolved at runtime via
# the `agentbox.guardrails` group).
COPY libs/cvman_agentbox /opt/cvman_agentbox
RUN pip install --no-cache-dir -e /opt/cvman_agentbox --config-settings editable_mode=compat

RUN mkdir -p /data /project /home/appuser/.claude /home/appuser/.local/share/opencode \
 && chown -R appuser:appuser /data /opt/agentbox /opt/cvman_agentbox /home/appuser/.claude /home/appuser/.local

COPY <<'EOF' /usr/local/bin/agentbox-entrypoint
#!/usr/bin/env bash
set -e
# Apply the project-supplied user config to Claude Code's state file at
# $CLAUDE_CONFIG_DIR/.claude.json. We MERGE on top of whatever Claude already
# wrote so OAuth state (userID, oauthAccount) is preserved across restarts.
# `projects` entries are merged so the project can add trusted workspace
# paths without dropping any the user has accepted manually.
PROJECT_CLAUDE_USER_CONFIG="/agentbox/claude-user-config.json"
CLAUDE_STATE="${CLAUDE_CONFIG_DIR:-/home/appuser/.claude}/.claude.json"
if [[ -f "$PROJECT_CLAUDE_USER_CONFIG" ]]; then
  mkdir -p "$(dirname "$CLAUDE_STATE")"
  python3 - "$CLAUDE_STATE" "$PROJECT_CLAUDE_USER_CONFIG" <<'PY'
import json, sys
from pathlib import Path
state_path, project_path = (Path(p) for p in sys.argv[1:3])
state = {}
if state_path.exists():
    try:
        state = json.loads(state_path.read_text())
    except Exception:
        state = {}
project = json.loads(project_path.read_text())
merged_projects = dict(state.get("projects", {}))
merged_projects.update(project.get("projects", {}))
overlay = {k: v for k, v in project.items() if k != "projects"}
state.update(overlay)
if merged_projects:
    state["projects"] = merged_projects
state_path.write_text(json.dumps(state, indent=2) + "\n")
PY
  echo "agentbox: applied project user config to $CLAUDE_STATE"
fi

# Memory symlink: if host-memory is mounted, link Claude's expected memory path
# to it so containerized agents share MEMORY.md with the host Claude session.
# HOST_PROJECT_DIR must be set (by docker-compose.override.yml) to the host
# project root so we can derive Claude's project-path-encoding (dashes for
# slashes) — e.g. /home/omidev/Code/ai/cv_agents → -home-omidev-Code-ai-cv-agents.
HOST_MEMORY_DIR="/agentbox/host-memory/projects"
if [[ -d "$HOST_MEMORY_DIR" && -n "${HOST_PROJECT_DIR:-}" ]]; then
  PROJECT_PATH="$(echo "$HOST_PROJECT_DIR" | tr '/' '-')"
  PROJECT_MEMORY_SRC="${HOST_MEMORY_DIR}/${PROJECT_PATH}/memory"
  CLAUDE_MEMORY_DST="${CLAUDE_CONFIG_DIR:-/home/appuser/.claude}/projects/${PROJECT_PATH}/memory"
  if [[ -d "$PROJECT_MEMORY_SRC" && ! -e "$CLAUDE_MEMORY_DST" ]]; then
    mkdir -p "$(dirname "$CLAUDE_MEMORY_DST")"
    ln -sf "$PROJECT_MEMORY_SRC" "$CLAUDE_MEMORY_DST"
    echo "agentbox: linked host memory → $CLAUDE_MEMORY_DST"
  fi
fi

exec "$@"
EOF
RUN chmod +x /usr/local/bin/agentbox-entrypoint

USER appuser
VOLUME ["/data", "/project"]
EXPOSE 8765

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/agentbox-entrypoint"]
CMD ["agentbox", "serve", "--host", "0.0.0.0", "--port", "8765"]
