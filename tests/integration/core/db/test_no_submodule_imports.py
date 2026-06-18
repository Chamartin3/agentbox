"""CI guard: external code must import from ``agentbox.core.data``, not its submodules.

The façade re-exports every public symbol (see ``test_facade_exports.py``).
Reaching into ``agentbox.core.db.<sub>`` from outside the package locks
callers to the current layout and blocks the consolidation work in
``docs/plans/24-core-data-consolidation.md``.

The only allowed external direct-submodule import is this test file's own
fixture for asserting the rule — and ``test_facade_exports.py`` which
intentionally re-imports ``SessionStore`` from its submodule to verify
the façade points at the same object.
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
    REPO_ROOT / "src" / "agentbox" / "core" / "data",
    # Tests that verify the façade itself by comparing against submodule.
    REPO_ROOT / "tests" / "data" / "test_facade_exports.py",
    REPO_ROOT / "tests" / "data" / "test_metadata_tables.py",
    # This guard.
    REPO_ROOT / "tests" / "data" / "test_no_submodule_imports.py",
}

PATTERN = re.compile(r"\bfrom\s+agentbox\.core\.data\.[a-z_][a-z_0-9]*\s+import\b")


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
                    offenders.append((path.relative_to(REPO_ROOT), lineno, line.strip()))

    if offenders:
        formatted = "\n".join(
            f"  {p}:{n}: {src}" for p, n, src in offenders
        )
        msg = (
            "Direct submodule imports of agentbox.core.data found. Use the "
            "package façade instead:\n"
            "  from agentbox.core.db import <name>\n\n"
            f"Offenders:\n{formatted}"
        )
        raise AssertionError(msg)
