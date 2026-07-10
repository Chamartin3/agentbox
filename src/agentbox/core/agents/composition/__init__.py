"""Agent prompt composition and resolution.

Public facade for the prompt pipeline: building composed prompts,
resolving resource bindings, rendering previews, and validating output.
"""

from agentbox.core.agents.composition.build import (
    build_prompt,
    build_runtime_view,
    resolve_agent_prompt_bindings,
)
from agentbox.core.agents.composition.bundle import (
    Bundle,
    BindingsBundleSource,
    BundleSource,
    ComposedReference,
    ComposeResult,
    compose,
    compose_from_source,
    load_bundle_from_bindings,
    precompose_check,
    validate_input,
    ReferenceSpec,
    OutputSchemaInfo,
)
from agentbox.core.agents.composition.preview import (
    CompositionPreview,
    PreviewError,
    ReferencePreview,
    preview,
    render_agent_prompt_preview,
)
from agentbox.core.agents.composition.resolver import (
    resolve_prompt,
)
from agentbox.core.agents.composition.rendering import (
    render_document,
    render_folder_manifest,
    render_for_type,
    render_schema,
    render_script,
    render_skill_primer,
)

__all__ = [
    "build_prompt",
    "build_runtime_view",
    "resolve_agent_prompt_bindings",
    "Bundle",
    "BindingsBundleSource",
    "BundleSource",
    "ComposedReference",
    "ComposeResult",
    "compose",
    "compose_from_source",
    "load_bundle_from_bindings",
    "precompose_check",
    "validate_input",
    "ReferenceSpec",
    "OutputSchemaInfo",
    "CompositionPreview",
    "PreviewError",
    "ReferencePreview",
    "preview",
    "render_agent_prompt_preview",
    "resolve_prompt",
    "render_document",
    "render_folder_manifest",
    "render_for_type",
    "render_schema",
    "render_script",
    "render_skill_primer",
]
