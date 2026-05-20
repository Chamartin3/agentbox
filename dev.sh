#!/usr/bin/env bash
# =============================================================================
# agentbox dev.sh — unified development command runner
# =============================================================================
# All administrative tasks for agentbox in the cv_agents dev environment:
# database migrations, frontend rebuilds, container lifecycle, lint/test,
# ownership fixes, CLI access. Run from anywhere; the script re-roots itself.
#
# Usage: ./dev.sh <command> [args...]   (or `./dev.sh help`)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# cv_agents root (libs/agentbox → ../..) — this is where docker-compose.yml lives.
CV_AGENTS_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
# Note: bash UID is readonly; docker compose reads these as env vars, so
# export GID and pass UID inline on docker compose calls via `env`.
export GID="$HOST_GID"

AGENTBOX_CONTAINER="${AGENTBOX_CONTAINER_NAME:-cvagents-agentbox}"
AGENTBOX_MCP_CONTAINER="${AGENTBOX_MCP_CONTAINER_NAME:-cvagents-agentbox-mcp}"
DIST_DIR="${SCRIPT_DIR}/src/agentbox/ui/static/dist"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()      { echo -e "${GREEN}[ OK ]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()     { echo -e "${RED}[ERR ]${NC} $*" >&2; }
header()  { echo -e "\n${CYAN}=== $* ===${NC}"; }

# Compose helper: always uses the cv_agents root compose stack.
compose() { (cd "$CV_AGENTS_ROOT" && env UID="$HOST_UID" GID="$HOST_GID" docker compose "$@"); }

# Detect if the container is running.
container_running() {
  docker ps --filter "name=^${AGENTBOX_CONTAINER}\$" --format '{{.Names}}' 2>/dev/null \
    | grep -q "^${AGENTBOX_CONTAINER}$"
}

# ---------------------------------------------------------------------------
# Container lifecycle
# ---------------------------------------------------------------------------

cmd_up() {
  header "starting agentbox stack"
  compose up -d --no-deps agentbox "$@"
  ok "started ${AGENTBOX_CONTAINER}"
}

cmd_down() {
  header "stopping agentbox stack"
  compose stop agentbox "${AGENTBOX_MCP_CONTAINER##cvagents-}" 2>/dev/null || true
  compose stop agentbox 2>/dev/null || true
}

cmd_restart() {
  header "recreating ${AGENTBOX_CONTAINER}"
  compose up -d --force-recreate --no-deps agentbox
  ok "recreated"
}

cmd_logs() {
  compose logs -f --tail=100 agentbox "$@"
}

cmd_status() {
  header "agentbox containers"
  docker ps --filter "name=${AGENTBOX_CONTAINER}" --filter "name=${AGENTBOX_MCP_CONTAINER}" \
    --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
}

# ---------------------------------------------------------------------------
# Build / frontend
# ---------------------------------------------------------------------------

cmd_fix_perms() {
  # `dist/` ends up root-owned when older container builds wrote into it.
  # vite's `emptyOutDir` then EACCES on the next build.
  if [[ -d "$DIST_DIR" ]]; then
    if [[ -w "$DIST_DIR" && "$(stat -c %u "$DIST_DIR")" == "$HOST_UID" ]]; then
      ok "dist already owned by $HOST_UID"
      return 0
    fi
    info "chowning $DIST_DIR → $HOST_UID:$HOST_GID via busybox (no host sudo needed)"
    docker run --rm -v "${DIST_DIR}:/dist" busybox \
      chown -R "${HOST_UID}:${HOST_GID}" /dist
    ok "dist ownership fixed"
  else
    info "no dist dir yet, nothing to fix"
  fi
}

cmd_rebuild_web() {
  header "rebuilding agentbox image (multi-stage: vite + python install)"
  cmd_fix_perms
  compose build --no-cache agentbox
  compose up -d --force-recreate --no-deps agentbox
  ok "image rebuilt + container recreated — hard-refresh http://localhost:8765/ (Ctrl-Shift-R)"
}

cmd_rebuild() {
  # Faster than --no-cache when only Python or web source changed.
  header "rebuilding agentbox image (cached)"
  cmd_fix_perms
  compose build agentbox
  compose up -d --force-recreate --no-deps agentbox
  ok "image rebuilt + container recreated"
}

# Full end-to-end build: image + container + migrations + web typecheck.
# Use this as the "make everything current" command after a pull or any
# multi-file edit that touches python + web + DB schema.
cmd_build() {
  header "full build: image + container + DB migrations + web typecheck"
  cmd_fix_perms
  info "1/4 — docker compose build agentbox"
  compose build agentbox
  info "2/4 — recreate container"
  compose up -d --force-recreate --no-deps agentbox
  # Wait for the container to be ready before running alembic in it.
  local i=0
  until container_running && docker exec "$AGENTBOX_CONTAINER" true 2>/dev/null; do
    ((i++)); [[ $i -gt 30 ]] && { err "container failed to come up"; exit 1; }
    sleep 1
  done
  info "3/4 — alembic upgrade head"
  alembic_in_container upgrade head
  info "4/4 — web typecheck (host)"
  if [[ -d "${SCRIPT_DIR}/web/node_modules" ]]; then
    (cd "${SCRIPT_DIR}/web" && ./node_modules/.bin/tsc --noEmit) \
      && ok "web typecheck clean" \
      || warn "web typecheck failed — fix before next session"
  else
    warn "web/node_modules missing — skipping typecheck (run: cd web && npm install)"
  fi
  ok "full build complete — http://localhost:8765/ (hard-refresh: Ctrl-Shift-R)"
}

cmd_web_dev() {
  header "starting vite dev server (host node)"
  cmd_fix_perms
  (cd "${SCRIPT_DIR}/web" && npm install && npm run dev)
}

cmd_web_typecheck() {
  (cd "${SCRIPT_DIR}/web" && ./node_modules/.bin/tsc --noEmit)
  ok "web typecheck clean"
}

# ---------------------------------------------------------------------------
# Database / Alembic
# ---------------------------------------------------------------------------

run_in_container() {
  if ! container_running; then
    err "${AGENTBOX_CONTAINER} is not running. Run: ./dev.sh up"
    exit 1
  fi
  docker exec -i "$AGENTBOX_CONTAINER" "$@"
}

# Run alembic inside the container with CWD=/data so the relative
# sqlite URL in alembic.ini (`sqlite:///./agentbox.sqlite`) resolves to
# the mounted /data volume.
alembic_in_container() {
  run_in_container bash -lc 'cd /data && alembic -c /opt/agentbox/alembic.ini "$@"' _ "$@"
}

cmd_migrate() {
  header "alembic upgrade ${1:-head}"
  alembic_in_container upgrade "${1:-head}"
  ok "migrations applied"
}

cmd_migrate_down() {
  local target="${1:-base}"
  warn "downgrading alembic to: $target"
  alembic_in_container downgrade "$target"
}

cmd_migrate_current() {
  alembic_in_container current
}

cmd_migrate_history() {
  alembic_in_container history "$@"
}

cmd_migrate_create() {
  local msg="${1:-}"
  if [[ -z "$msg" ]]; then
    err "usage: ./dev.sh migrate-create '<short description>'"
    exit 1
  fi
  header "creating alembic revision: $msg"
  # --autogenerate diffs models vs DB. New file lands in
  # libs/agentbox/alembic/versions/ via the bind mount.
  alembic_in_container revision --autogenerate -m "$msg"
  ok "revision created — review the file in alembic/versions/ before running 'migrate'"
}

cmd_db_shell() {
  header "sqlite shell on agentbox-data volume"
  run_in_container sqlite3 /data/agentbox.sqlite
}

cmd_db_backup() {
  local stamp; stamp="$(date +%Y%m%d-%H%M%S)"
  local dest="${SCRIPT_DIR}/backups/agentbox-${stamp}.sqlite"
  mkdir -p "${SCRIPT_DIR}/backups"
  run_in_container sqlite3 /data/agentbox.sqlite ".backup /data/_backup.sqlite"
  docker cp "${AGENTBOX_CONTAINER}:/data/_backup.sqlite" "$dest"
  run_in_container rm -f /data/_backup.sqlite
  ok "backup → $dest"
}

# ---------------------------------------------------------------------------
# Shell / CLI / tests
# ---------------------------------------------------------------------------

cmd_shell() {
  if ! container_running; then
    err "${AGENTBOX_CONTAINER} is not running. Run: ./dev.sh up"
    exit 1
  fi
  docker exec -it "$AGENTBOX_CONTAINER" bash
}

cmd_cli() {
  run_in_container agentbox "$@"
}

cmd_test() {
  header "pytest (in container)"
  run_in_container bash -c "cd /opt/agentbox && uv run pytest $*"
}

cmd_check() {
  header "ruff check + pyright (in container)"
  run_in_container bash -c "cd /opt/agentbox && uv run ruff check src tests && uv run pyright src"
  ok "lint + typecheck clean"
}

cmd_fix() {
  header "ruff fix + format (in container)"
  run_in_container bash -c "cd /opt/agentbox && uv run ruff check --fix src tests && uv run ruff format src tests"
}

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

cmd_help() {
  cat <<'HELP'
agentbox dev.sh — unified developer command runner

Container lifecycle
  up                  Start agentbox container (docker compose up -d)
  down                Stop agentbox + agentbox-mcp containers
  restart             Force-recreate the agentbox container
  status              Show agentbox container status
  logs [args...]      Tail logs (-f, --tail=100 by default)

Build & frontend
  build               Full build: image + container + migrate + web typecheck
  rebuild             Cached docker build + recreate (fast; use after Python edits)
  rebuild-web         Full --no-cache rebuild (slower; use after web/ edits)
  fix-perms           Chown dist/ back to host user (fixes EACCES from vite)
  web-dev             Run vite dev server on host (live reload, port 5173)
  web-typecheck       Run `tsc --noEmit` on web/

Database & Alembic
  migrate [rev]       alembic upgrade (default: head)
  migrate-down [rev]  alembic downgrade (default: base — destructive)
  migrate-current     Show current DB revision
  migrate-history     Show migration history
  migrate-create MSG  alembic revision --autogenerate -m "MSG"
  db-shell            sqlite3 shell on /data/agentbox.sqlite
  db-backup           Copy DB to backups/agentbox-<stamp>.sqlite

Code quality & tests
  test [args...]      uv run pytest (in container)
  check               ruff check + pyright (in container)
  fix                 ruff --fix + ruff format (in container)

Misc
  shell               Interactive bash in the agentbox container
  cli ARGS            Run the `agentbox` CLI inside the container
  help                Show this message

Env overrides
  AGENTBOX_CONTAINER_NAME   override container name (default: cvagents-agentbox)
HELP
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

main() {
  local cmd="${1:-help}"; shift || true
  case "$cmd" in
    up)               cmd_up "$@" ;;
    down)             cmd_down "$@" ;;
    restart)          cmd_restart ;;
    status)           cmd_status ;;
    logs)             cmd_logs "$@" ;;

    build)            cmd_build ;;
    rebuild)          cmd_rebuild ;;
    rebuild-web)      cmd_rebuild_web ;;
    fix-perms)        cmd_fix_perms ;;
    web-dev)          cmd_web_dev ;;
    web-typecheck)    cmd_web_typecheck ;;

    migrate)          cmd_migrate "$@" ;;
    migrate-down)     cmd_migrate_down "$@" ;;
    migrate-current)  cmd_migrate_current ;;
    migrate-history)  cmd_migrate_history "$@" ;;
    migrate-create)   cmd_migrate_create "$@" ;;
    db-shell)         cmd_db_shell ;;
    db-backup)        cmd_db_backup ;;

    test)             cmd_test "$@" ;;
    check)            cmd_check ;;
    fix)              cmd_fix ;;

    shell)            cmd_shell ;;
    cli)              cmd_cli "$@" ;;

    help|-h|--help)   cmd_help ;;
    *)                err "unknown command: $cmd"; cmd_help; exit 2 ;;
  esac
}

main "$@"
