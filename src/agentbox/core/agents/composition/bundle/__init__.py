"""Prompt composition — shared bundle renderer for agentbox and callers.

Re-exports public symbols from sub-modules. Import from here:
``from agentbox.core.agents.composition.bundle import compose, preview``.
"""

from agentbox.core.agents.composition.bundle._helpers import (
    _append_input_schema,
    _append_schema,
    _append_validation_engine_hint,
)
from agentbox.core.agents.composition.bundle.compose import (
    ComposeResult,
    ComposedReference,
    compose,
    compose_from_source,
)
from agentbox.core.agents.composition.bundle.preview import (
    CompositionPreview,
    ReferencePreview,
    preview,
)
from agentbox.core.agents.composition.bundle.sources import (
    BindingsBundleSource,
    BundleSource,
)

__all__ = [
    "BindingsBundleSource",
    "BundleSource",
    "ComposeResult",
    "ComposedReference",
    "CompositionPreview",
    "ReferencePreview",
    "compose",
    "compose_from_source",
    "preview",
]
