# Multi-stage: build the React SPA, then assemble the Python runtime.

FROM node:20-alpine AS web
WORKDIR /web
COPY web/package.json ./
RUN npm install --no-audit --no-fund
COPY web/ ./
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

# Base tools. Node comes from NodeSource (not Debian's Node 20 LTS) because
# some bundled backend CLIs need Node 21+ APIs (e.g. undici's markAsUncloneable).
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

# Backend agent CLIs — installed at build time so they're part of the image
# layer (not the runtime volume). The specific set lives in the script so
# this Dockerfile names no backend; edit docker/install-backends.sh to change
# which backends ship.
COPY docker/install-backends.sh /usr/local/bin/install-backends
RUN chmod +x /usr/local/bin/install-backends && install-backends

WORKDIR /opt/agentbox
COPY pyproject.toml ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

# Drop the SPA into the place FastAPI expects.
COPY --from=web /web/dist /opt/agentbox/src/agentbox/ui/static/dist

RUN pip install --no-cache-dir -e . websockets

# Writable, appuser-owned dirs. The opencode state dir is pre-created so that
# consumers bind-mounting an auth.json into ~/.local/share/opencode/ don't make
# Docker auto-create the parent chain as root — which would leave opencode (the
# appuser process) unable to mkdir its log/repos siblings at runtime.
RUN mkdir -p /data /project /home/appuser/.local/share/opencode /home/appuser/.config/opencode \
 && chown -R appuser:appuser /data /opt/agentbox /home/appuser

# Generic entrypoint runs any drop-in bootstrap scripts then execs the CMD.
# agentbox ships none — backends set up via their credentials system + the
# creds volume. A consumer needing extra init mounts scripts into
# /agentbox/entrypoint.d/ (see docker/entrypoint.sh).
COPY docker/entrypoint.sh /usr/local/bin/agentbox-entrypoint
RUN chmod +x /usr/local/bin/agentbox-entrypoint

USER appuser
VOLUME ["/data", "/project"]
EXPOSE 8765

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/agentbox-entrypoint"]
CMD ["agentbox", "serve", "--host", "0.0.0.0", "--port", "8765"]
