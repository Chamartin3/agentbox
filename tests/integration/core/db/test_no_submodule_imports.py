"""CI guard: APPLICATION code must import from ``agentbox.core.db``, not its submodules.

The façade re-exports every public manager. Reaching into
``agentbox.core.db.<sub>`` from application code locks callers to the current
layout and blocks the consolidation work in
``docs/plans/24-core-data-consolidation.md``.

Scope: only ``src/`` (plus ``alembic``/``bin``) is checked — see ``SEARCH_ROOTS``.
Tests are NOT held to this rule; they may use specific submodule imports
(``Database``, schema tables, a manager module for patching).

Plan 109 exception: ``agentbox.core.db.database`` is intentionally importable
from the named allowlist below (composition roots and DI singletons).  These
are tracked as debt in importlinter ``db-facade-managers-only`` and burned by
plans 111/112/110/113_04.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Only the APPLICATION is held to facade-only imports. Tests may reach into
# ``agentbox.core.db`` subbranches (e.g. import ``Database`` / schema tables /
# a manager module for patching) — they are allowed specific imports.
SEARCH_ROOTS = (
    REPO_ROOT / "src",
    REPO_ROOT / "alembic",
    REPO_ROOT / "bin",
)

# Files allowed to reach into submodules.
ALLOWED = {
    # Internal to the package — its own modules legitimately import siblings.
    REPO_ROOT / "src" / "agentbox" / "core" / "db",
    # Alembic is the schema's own migration tooling, not application code: the
    # baseline runs ``metadata.create_all`` and needs ``core.db.schema.metadata``
    # (the facade is managers-only and does not re-export it).
    REPO_ROOT / "alembic",
    # Lifecycle imports that reach into data submodules (pre-existing).
    REPO_ROOT / "src" / "agentbox" / "core" / "service" / "lifecycle.py",
    # ── plan 109 Phase A debt: core.db.database allowlist ──────────────────
    # These files import ``from agentbox.core.db.database import Database/get_database``
    # because Database/get_database are no longer facade-exported. Each site is
    # tracked in importlinter db-facade-managers-only.ignore_imports and burned
    # by plans 111/112/110/113_04.
    # Permanent (composition roots):
    REPO_ROOT / "src" / "agentbox" / "core" / "service" / "base.py",
    # Transitional cli commands:
    REPO_ROOT / "src" / "agentbox" / "cli" / "ops" / "shell.py",
    # Transitional mcp/server contexts (burned by plan 110):
    REPO_ROOT / "src" / "agentbox" / "core" / "tools" / "mcp_servers" / "agent_tools" / "context.py",
    REPO_ROOT / "src" / "agentbox" / "core" / "tools" / "mcp_servers" / "host_env" / "context.py",
    # Transitional core domain users (burned by plans 111/112):
    REPO_ROOT / "src" / "agentbox" / "core" / "execution" / "orchestrate" / "executor.py",
    REPO_ROOT / "src" / "agentbox" / "core" / "execution" / "observability" / "snapshot" / "runner.py",
    REPO_ROOT / "src" / "agentbox" / "core" / "engines" / "profiles.py",
    REPO_ROOT / "src" / "agentbox" / "core" / "service" / "engines" / "providers.py",
    # Transitional service/workspace modules:
    REPO_ROOT / "src" / "agentbox" / "api" / "workspaces" / "crud.py",
    REPO_ROOT / "src" / "agentbox" / "core" / "service" / "lifecycle" / "startup.py",
    REPO_ROOT / "src" / "agentbox" / "core" / "service" / "workspaces" / "registry.py",
}

# ``core.db.config`` is a public self-wiring read-helper module (not a manager,
# so it is not facade-exported) — application code imports it directly, by
# design (plan 127 moved it up from the old ``core.db.system.config``). Exclude
# it from the guard; every other single-segment ``core.db.<sub>`` is held.
PATTERN = re.compile(r"\bfrom\s+agentbox\.core\.db\.(?!config\b)[a-z_][a-z_0-9]*\s+import\b")


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
