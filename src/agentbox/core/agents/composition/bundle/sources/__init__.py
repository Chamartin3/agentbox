"""Bundle sources — decouple the composer from the storage backend.

A ``BundleSource`` is anything that can answer "give me the bytes for this
bundle's system prompt, user template, references, and output schema".
``BindingsBundleSource`` is the only implementation: it reads from
``agent_prompt_resource_bindings``, which is the single source of truth
post-bundle deprecation.
"""

from agentbox.core.agents.composition.bundle.sources._types import (
    BundleSource as BundleSource,
    OutputSchemaInfo as OutputSchemaInfo,
    ReferenceSpec as ReferenceSpec,
)
from agentbox.core.agents.composition.bundle.sources.bindings import (
    BindingsBundleSource as BindingsBundleSource,
)

__all__ = [
    "BundleSource",
    "BindingsBundleSource",
    "OutputSchemaInfo",
    "ReferenceSpec",
]
