"""Bundle loader — turns an agent directory into a typed ``Bundle``.

Validates file existence at load time so missing references are caught
early, before the runner is invoked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentbox.core.data import CompositionConfig
from agentbox.core.agent.prompt.composition import (
    ComposeResult,
    compose_from_source,
)
from agentbox.core.agent.prompt.composition.sources import (
    BindingsBundleSource,
    BundleSource,
)

logger = logging.getLogger(__name__)


@dataclass
class Bundle:
    """Self-contained agent bundle ready for composition.

    DB-backed only: carries a ``BundleSource`` built from
    ``agent_prompt_resource_bindings``. ``path`` is retained for
    backward-compatible introspection but is always ``None`` at runtime.
    """

    agent_id: str
    path: Path | None = None
    composition: CompositionConfig | None = None
    source: BundleSource | None = None

    def compose(
        self,
        variables: dict[str, str],
        shared_roots: dict[str, Path] | None = None,
    ) -> ComposeResult:
        if self.source is None:
            raise ValueError(f"Bundle for {self.agent_id!r} has no source")
        return compose_from_source(self.source, variables)


def load_bundle_from_bindings(
    agent_id: str,
    store: Any,
) -> Bundle:
    """Build a Bundle backed by agent_prompt_resource_bindings.

    DB-as-source-of-truth (Plan 18): composition state comes from
    bindings, with a fallback to ``agent_versions.prompt_content``
    when no slot='system' binding exists. The on-disk bundle is
    never consulted at runtime.
    """
    source = BindingsBundleSource(agent_id=agent_id, store=store)
    # Synthesize a CompositionConfig from the source's composition dict so
    # downstream callers that introspect ``bundle.composition`` keep
    # working. Unknown fields are dropped by model_validate.
    composition = CompositionConfig.model_validate(source.composition)
    return Bundle(
        agent_id=agent_id,
        path=None,
        composition=composition,
        source=source,
    )
