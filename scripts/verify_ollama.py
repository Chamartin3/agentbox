#!/usr/bin/env python
"""Plan 16 Phase 1.4 — manual verification driver against a live Ollama.

Drives the token backend through the EVENT_PARITY scenarios end-to-end
and prints a pass/fail table. Requires ``OLLAMA_HOST`` to be set; bring
the model server up first with::

    docker compose --profile verify up -d ollama ollama-seed
    OLLAMA_HOST=http://localhost:11434 python scripts/verify_ollama.py

This is intentionally thin — under the hood it just calls
``pytest tests/integration/test_ollama_live.py`` with verbose output
and a summary banner. As Phase 1.3 grows more scenarios, add them to
``test_ollama_live.py`` and they show up here automatically.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    if "OLLAMA_HOST" not in os.environ:
        print("ERROR: OLLAMA_HOST is not set", file=sys.stderr)
        print(
            "  hint: docker compose --profile verify up -d ollama ollama-seed\n"
            "        OLLAMA_HOST=http://localhost:11434 python scripts/verify_ollama.py",
            file=sys.stderr,
        )
        return 2

    root = Path(__file__).resolve().parent.parent
    started = time.monotonic()
    print("agentbox verification — Ollama")
    print("═" * 60)
    print(f"OLLAMA_HOST = {os.environ['OLLAMA_HOST']}")
    print()

    proc = subprocess.run(
        [
            "uv",
            "run",
            "pytest",
            "tests/integration/test_ollama_live.py",
            "-v",
            "-m",
            "live_ollama",
        ],
        cwd=root,
        check=False,
    )

    elapsed = time.monotonic() - started
    print()
    print("─" * 60)
    print(f"elapsed: {elapsed:.1f}s   exit={proc.returncode}")
    if proc.returncode == 0:
        print("RESULT: ✔ all scenarios pass")
    else:
        print("RESULT: ✘ one or more scenarios failed — see pytest output above")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
