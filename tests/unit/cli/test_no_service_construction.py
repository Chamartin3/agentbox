"""Guard: CLI commands access Services via CLIContext, never by construction.

Commands and renderers must reach Services through ``ctx.obj`` (see
workdir/rules/cli-commands.md). Constructing ``XService()`` inline
bypasses the DI context — import-linter can't catch it (the import is
legal for type hints), so this test greps for the call pattern.
"""

from __future__ import annotations

import re
from pathlib import Path

CLI_ROOT = Path(__file__).parents[3] / "src" / "agentbox" / "cli"

# Files allowed to construct Services: the DI composition root only.
_ALLOWED = {"shared/deps.py", "shared/context.py"}

# ponytail: launch.py litter is owned by plan 101_02 (launch_full_ctx_migration);
# remove this entry when that plan lands.
_KNOWN_DEBT = {"ops/launch.py"}

_CONSTRUCTION = re.compile(r"\b[A-Z]\w*Service\(\)")


def test_no_inline_service_construction() -> None:
    offenders: list[str] = []
    for path in CLI_ROOT.rglob("*.py"):
        rel = path.relative_to(CLI_ROOT).as_posix()
        if rel in _ALLOWED or rel in _KNOWN_DEBT:
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if _CONSTRUCTION.search(line):
                offenders.append(f"cli/{rel}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Service constructed inline in CLI (use ctx.obj.<service> instead):\n"
        + "\n".join(offenders)
    )
