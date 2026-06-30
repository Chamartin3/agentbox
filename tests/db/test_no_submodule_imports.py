"""CI guard: external code must import from ``agentbox.core.db``, not its submodules.

The façade re-exports every public symbol (see ``test_facade_exports.py``).
Reaching into ``agentbox.core.db.<sub>`` from outside the package locks
callers to the current layout and blocks the consolidation work in
``docs/plans/24-core-data-consolidation.md``.

The only allowed external direct-submodule import is this test file's own
fixture for asserting the rule — and ``test_facade_exports.py`` which
intentionally re-imports ``SessionStore`` from its submodule to verify
the façade points at the same object.

Plan 109 exception: ``agentbox.core.db.database`` is intentionally importable
from the named allowlist below (composition roots and DI singletons).  These
are tracked as debt in importlinter ``db-facade-managers-only`` and burned by
plans 111/112/110/113_04.  ``agentbox.core.db.schema`` is similarly tolerated
in service/execution modules that haven't yet migrated to managers.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SEARCH_ROOTS = (
    REPO_ROOT / "src",
    REPO_ROOT / "tests",
    REPO_ROOT / "alembic",
    REPO_ROOT / "bin",
)

# Files allowed to reach into submodules.
ALLOWED = {
    # Internal to the package — its own modules legitimately import siblings.
    REPO_ROOT / "src" / "agentbox" / "core" / "db",
    # Lifecycle imports that reach into data submodules (pre-existing).
    REPO_ROOT / "src" / "agentbox" / "core" / "service" / "lifecycle.py",
    # Tests that verify the façade itself by comparing against submodule.
    REPO_ROOT / "tests" / "db" / "test_facade_exports.py",
    REPO_ROOT / "tests" / "db" / "test_metadata_tables.py",
    # Tests that need direct module access for mocking.
    REPO_ROOT / "tests" / "db" / "test_mcp_discovery_cache.py",
    # Integration / unit tests that access submodules directly by design.
    REPO_ROOT / "tests" / "integration" / "core" / "db" / "test_facade_exports.py",
    REPO_ROOT / "tests" / "integration" / "core" / "db" / "test_metadata_tables.py",
    REPO_ROOT / "tests" / "unit" / "core" / "db" / "test_records.py",
    REPO_ROOT / "tests" / "unit" / "core" / "data" / "test_manifest.py",
    REPO_ROOT / "tests" / "unit" / "core" / "agents" / "test_manifest.py",
    # This guard.
    REPO_ROOT / "tests" / "db" / "test_no_submodule_imports.py",
    # ── plan 109 Phase A debt: core.db.database allowlist ──────────────────
    # These files import ``from agentbox.core.db.database import Database/get_database``
    # because Database/get_database are no longer facade-exported. Each site is
    # tracked in importlinter db-facade-managers-only.ignore_imports and burned
    # by plans 111/112/110/113_04.
    # Permanent (composition roots):
    REPO_ROOT / "src" / "agentbox" / "core" / "service" / "base.py",
    # Transitional DI singletons (burned by plan 113_04):
    REPO_ROOT / "src" / "agentbox" / "api" / "deps.py",
    REPO_ROOT / "src" / "agentbox" / "cli" / "shared" / "deps.py",
    REPO_ROOT / "src" / "agentbox" / "mcp" / "deps.py",
    # Transitional cli commands:
    REPO_ROOT / "src" / "agentbox" / "cli" / "ops" / "shell.py",
    # Transitional mcp/server contexts (burned by plan 110):
    REPO_ROOT / "src" / "agentbox" / "core" / "workspaces" / "mcp" / "servers" / "agent_tools" / "context.py",
    REPO_ROOT / "src" / "agentbox" / "core" / "workspaces" / "mcp" / "servers" / "host_env" / "context.py",
    # Transitional core domain users (burned by plans 111/112):
    REPO_ROOT / "src" / "agentbox" / "core" / "execution" / "orchestrate" / "executor.py",
    REPO_ROOT / "src" / "agentbox" / "core" / "execution" / "observability" / "snapshot" / "runner.py",
    REPO_ROOT / "src" / "agentbox" / "core" / "agents" / "composition" / "drift.py",
    REPO_ROOT / "src" / "agentbox" / "core" / "engines" / "profiles.py",
    REPO_ROOT / "src" / "agentbox" / "core" / "service" / "engines" / "providers.py",
    # ── plan 109 Phase A debt: core.db.schema allowlist ────────────────────
    # These import schema tables directly; burned by plans 111/112.
    REPO_ROOT / "src" / "agentbox" / "core" / "execution" / "orchestrate" / "init_run.py",
    REPO_ROOT / "src" / "agentbox" / "core" / "service" / "agents" / "crud.py",
    # ── plan 109 Phase A debt: test files that must use submodule paths ────
    REPO_ROOT / "tests" / "db" / "test_managers.py",
    REPO_ROOT / "tests" / "db" / "test_models.py",
    REPO_ROOT / "tests" / "conftest.py",
    REPO_ROOT / "tests" / "integration" / "conftest.py",
    REPO_ROOT / "tests" / "e2e" / "conftest.py",
    REPO_ROOT / "tests" / "e2e" / "test_orphan_reap.py",
    REPO_ROOT / "tests" / "integration" / "api" / "test_agent_lifecycle_routes.py",
    REPO_ROOT / "tests" / "integration" / "core" / "agents" / "composition" / "test_prompt_sync.py",
    REPO_ROOT / "tests" / "integration" / "core" / "service" / "test_agent_service.py",
    REPO_ROOT / "tests" / "integration" / "core" / "db" / "test_agent_tool_grants.py",
    REPO_ROOT / "tests" / "integration" / "core" / "db" / "test_metadata_tables.py",
    REPO_ROOT / "tests" / "db" / "test_agent_tool_grants.py",
}

PATTERN = re.compile(r"\bfrom\s+agentbox\.core\.db\.[a-z_][a-z_0-9]*\s+import\b")


def _is_allowed(path: Path) -> bool:
    for allowed in ALLOWED:
        if path == allowed:
            return True
        if allowed.is_dir() and allowed in path.parents:
            return True
    return False


def test_no_external_submodule_imports() -> None:
    offenders: list[tuple[Path, int, str]] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if _is_allowed(path):
                continue
            for lineno, line in enumerate(path.read_text().splitlines(), start=1):
                if PATTERN.search(line):
                    offenders.append(
                        (path.relative_to(REPO_ROOT), lineno, line.strip())
                    )

    if offenders:
        formatted = "\n".join(f"  {p}:{n}: {src}" for p, n, src in offenders)
        msg = (
            "Direct submodule imports of agentbox.core.db found. Use the "
            "package façade instead:\n"
            "  from agentbox.core.db import <name>\n\n"
            f"Offenders:\n{formatted}"
        )
        raise AssertionError(msg)
