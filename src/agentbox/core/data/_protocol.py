"""Structural protocol describing the SessionStore surface mixins consume.

Each mixin in ``agentbox.core.data`` is composed into ``SessionStore``
alongside ``_CoreStore`` and ~19 sibling mixins. At authoring time a
mixin needs to call into store-internal attributes (``self.engine``)
and into helpers defined on *other* mixins. The mixin class itself has
no type information about those, so historically every cross-class
access carried ``# type: ignore[attr-defined]`` and every mixin file
imported ``SessionStore`` under ``TYPE_CHECKING`` purely to satisfy a
type checker.

``StoreContext`` is the structural contract those mixins rely on. By
typing ``self: StoreContext`` inside mixin methods, type checkers
resolve attribute access cleanly without a circular runtime import and
without per-line escape hatches. Only attributes/methods actually
consumed by a sibling mixin are declared here — this is a *consumer*
view of the store, not a mirror of every public API.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.engine import Engine


class StoreContext(Protocol):
    """Surface of ``SessionStore`` that sibling mixins read from."""

    # ----- _CoreStore connection state ------------------------------------
    engine: Engine

    # ----- cross-mixin / intra-mixin helpers ------------------------------
    # Methods declared here so that mixin code typed as ``self: StoreContext``
    # can still call sibling-mixin helpers AND its own helper methods. The
    # set is intentionally minimal — extend only when a new call site
    # appears.

    def get_repo_resource(self, resource_id: str) -> dict | None:
        """Defined on ``ResourcesMixin``; used by ``ResourceBindingsMixin``."""
        ...

    def list_workspace_file_bindings(self, workspace_id: str) -> list[dict]:
        """Defined on ``ResourceBindingsMixin``; used internally for re-reads."""
        ...

    def replace_workspace_file_bindings(
        self,
        workspace_id: str,
        bindings: object,
        *,
        reason: str,
        actor: str | None = None,
    ) -> list[dict]:
        """Defined on ``ResourceBindingsMixin``; invoked by skill replace."""
        ...

    def _get_grant_row(self, agent_id: str, tool_name: str) -> dict:
        """Internal helper on ``AgentToolGrantsMixin``."""
        ...

    def list_agent_tool_grants(
        self, agent_id: str, include_revoked: bool = False
    ) -> list[dict]:
        """Defined on ``AgentToolGrantsMixin``; called by ``list_active_grants``."""
        ...
