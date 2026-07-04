"""Guard: ensure ``core.data`` imports nothing above the leaf layer.

Every module under ``src/agentbox/core/data/**`` must NOT import from
prohibited packages — that is how we enforce the "no logic / leaf-only"
boundary.

Prohibited imports:
- ``core.db``, ``core.engines``, ``core.workspaces``
- ``core.service``, ``core.execution``
- ``agentbox.api``, ``agentbox.cli``
- ``sqlalchemy``
"""

from __future__ import annotations

import ast
from pathlib import Path

PROHIBITED_TOP_LEVEL = {
    "sqlalchemy",
}

PROHIBITED_MODULE_PREFIXES = (
    "agentbox.core.db",
    "agentbox.core.engines",
    "agentbox.core.workspaces",
    "agentbox.core.service",
    "agentbox.core.execution",
    "agentbox.api",
    "agentbox.cli",
)

DATA_ROOT = Path(__file__).resolve().parent.parent.parent / "src" / "agentbox" / "core" / "data"


def _find_py_files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*.py")
        if "__pycache__" not in str(p)
    )


def _collect_imports(filepath: Path) -> list[tuple[int, str]]:
    """Return list of (lineno, full_module_path) for every import."""
    with open(filepath, encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=str(filepath))
        except SyntaxError:
            return []

    imports: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((node.lineno or 0, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                imports.append((node.lineno or 0, node.module))
    return imports


def _is_prohibited(module: str) -> bool:
    top = module.split(".")[0]
    if top in PROHIBITED_TOP_LEVEL:
        return True
    for prefix in PROHIBITED_MODULE_PREFIXES:
        if module.startswith(prefix):
            return True
    return False


def test_data_imports_no_prohibited_packages() -> None:
    violations: list[str] = []
    for pyfile in _find_py_files(DATA_ROOT):
        rel = pyfile.relative_to(
            DATA_ROOT.parent.parent.parent.parent  # repo root
        )
        for lineno, module in _collect_imports(pyfile):
            if _is_prohibited(module):
                violations.append(f"{rel}:{lineno}  import {module}")

    if violations:
        msg = "\n".join(violations)
        raise AssertionError(
            f"core/data imports prohibited packages "
            f"({len(violations)} violation(s)):\n{msg}"
        )
