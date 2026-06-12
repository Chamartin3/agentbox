"""Materialize ``RenderedConfig.files`` into a run directory.

Moved from ``workspaces/prep.py`` (Plan 045_01 Phase B1).  The executor
owns materialization; workspaces owns only workspace-file generation.
"""

from __future__ import annotations

from pathlib import Path

from agentbox.core.engines.backends.rendered import RenderedConfig


def materialize_rendered_config(
    rendered: RenderedConfig,
    target_dir: Path,
) -> None:
    """Write rendered config files into ``target_dir`` with strict perms.

    ``target_dir`` must already exist (created by workspace preparation).
    Subdirectories are created as needed with mode 0o700; all files are
    written with mode 0o600.
    """
    for relpath, data in rendered.files.items():
        full = target_dir / relpath
        if full.parent != target_dir:
            full.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        full.write_bytes(data)
        full.chmod(0o600)
