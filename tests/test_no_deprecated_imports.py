"""Guard: nothing outside ``core/deprecated/`` may import from it.

The folder is named ``deprecated`` — by definition it is not part of the
live runtime. This test fails the moment any module under ``src/agentbox``
(other than the deprecated tree itself) re-introduces a dependency on it,
so the "deprecated" label and the import graph stay in agreement.

When this test goes green, ``core/deprecated/`` is safe to delete.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src" / "agentbox"
_DEPRECATED_PREFIX = _SRC / "core" / "deprecated"

_PATTERN = re.compile(
    r"^\s*(?:from\s+agentbox\.core\.deprecated|import\s+agentbox\.core\.deprecated)",
    re.MULTILINE,
)


def test_no_imports_from_core_deprecated() -> None:
    offenders: list[str] = []
    for path in _SRC.rglob("*.py"):
        try:
            path.relative_to(_DEPRECATED_PREFIX)
            continue  # files inside core/deprecated/ are allowed to self-reference
        except ValueError:
            pass
        text = path.read_text(encoding="utf-8")
        if _PATTERN.search(text):
            offenders.append(str(path.relative_to(_REPO_ROOT)))

    assert not offenders, (
        "core/deprecated/ must not participate in the live runtime. "
        f"Found {len(offenders)} importer(s):\n  - "
        + "\n  - ".join(sorted(offenders))
    )
