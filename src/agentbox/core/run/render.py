from __future__ import annotations

from pathlib import Path

from agentbox.core.engines.backends.base import RenderedConfig


class RunDirExists(RuntimeError):
    """Raised when the target run directory already exists."""


def materialize_rendered_config(
    rendered: RenderedConfig,
    target_dir: Path,
) -> None:
    """Write rendered config files into ``target_dir``, creating it exclusively.

    Raises ``RunDirExists`` if ``target_dir`` already exists — callers must
    supply a fresh (UUID-keyed) path per run.  All directories are created
    with mode 0o700; all files with mode 0o600.
    """
    try:
        target_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    except FileExistsError:
        raise RunDirExists(f"run directory already exists: {target_dir}") from None

    for relpath, data in rendered.files.items():
        full = target_dir / relpath
        if full.parent != target_dir:
            full.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        full.write_bytes(data)
        full.chmod(0o600)
