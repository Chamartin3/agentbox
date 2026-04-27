"""Manifest sync — file-system read/write for agent definitions.

This module contains **only** file I/O operations.  It does not touch the
database; the database model is the sole source of truth and decides when
to call these helpers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentbox.core.data.manifest import AgentDef
from agentbox.core.definitions import ManifestWriter

if TYPE_CHECKING:
    from agentbox.core.definitions.loader import DefinitionLoader

logger = logging.getLogger(__name__)


class ManifestSync:
    """Read and write agent definitions on disk.

    All methods are pure file-system operations.  Callers (usually the DB
    model) are responsible for deciding *when* to sync.
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._writer = ManifestWriter(project_root)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def read_agent(self, agent_id: str, loader: DefinitionLoader) -> AgentDef | None:
        """Load a single agent from the filesystem."""
        return loader.get(agent_id)

    def read_agent_from_path(self, path: Path) -> AgentDef | None:
        """Parse an agent definition at an explicit path."""
        if not path.exists():
            return None
        try:
            from agentbox.core.definitions.loader import DefinitionLoader

            loader = DefinitionLoader(self.project_root)
            # Re-use the internal loader logic by creating a temporary loader
            # scoped to this file.  For inline agents this falls back to the
            # full manifest scan.
            return loader.get(path.stem)
        except Exception:
            logger.exception("manifest_sync: failed to read agent from %s", path)
            return None

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write_agent(self, agent: AgentDef) -> Path:
        """Persist ``agent`` to its source file, dispatching by format.

        Returns the path written to.
        """
        return self._writer.save_agent(agent)

    def patch_agent(self, agent_id: str, patch: dict[str, Any]) -> AgentDef:
        """Apply a patch dict to the on-disk agent definition.

        Raises :class:`PatchError` on validation failure or missing file.
        """
        return self._writer.patch_agent(agent_id, patch)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def compute_file_hash(self, path: Path | None) -> str | None:
        import hashlib

        if path is None or not path.exists():
            return None
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return None

    def file_mtime(self, path: Path | None) -> str | None:
        if path is None or not path.exists():
            return None
        try:
            return str(path.stat().st_mtime)
        except OSError:
            return None
