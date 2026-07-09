"""Public facade for the prompt composition subtree.

Re-exports the names available from `core.agent.prompt.*` so external callers
import from one place.
"""

from agentbox.core.agents.composition.capture import (
    PromptFragment as PromptFragment,
    build_fragments as build_fragments,
    fragments_to_json as fragments_to_json,
)
from agentbox.core.agents.composition.bundle import (
    ComposeResult as ComposeResult,
    ComposedReference as ComposedReference,
    CompositionPreview as CompositionPreview,
    ReferencePreview as ReferencePreview,
    compose as compose,
    compose_from_source as compose_from_source,
    preview as preview,
)
from agentbox.core.agents.contract.render import (
    append as append_output_contract,
    render as render_output_contract,
)
from agentbox.core.agents.composition.preview import (
    PreviewError as PreviewError,
    render_agent_prompt_preview as render_agent_prompt_preview,
)
from agentbox.core.agents.composition.rendering import (
    render_document as render_document,
    render_folder_manifest as render_folder_manifest,
    render_for_type as render_for_type,
    render_schema as render_schema,
    render_script as render_script,
    render_skill_primer as render_skill_primer,
)
from agentbox.core.agents.composition.resolver import (
    PromptResolution as PromptResolution,
    ResolvedBinding as ResolvedBinding,
    resolve_prompt as resolve_prompt,
)

__all__ = [
    "ComposeResult",
    "ComposedReference",
    "CompositionPreview",
    "PreviewError",
    "PromptFragment",
    "PromptResolution",
    "ReferencePreview",
    "ResolvedBinding",
    "append_output_contract",
    "build_fragments",
    "compose",
    "compose_from_source",
    "fragments_to_json",
    "preview",
    "render_agent_prompt_preview",
    "render_document",
    "render_folder_manifest",
    "render_for_type",
    "render_output_contract",
    "render_schema",
    "render_script",
    "render_skill_primer",
    "resolve_prompt",
]
