"""Token backend config generator.

Produces a flat prompt.txt with everything inlined (system + skills + schema + user).
Uses PromptComposer for the shared assembly logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from agentbox.core.config_generation.backends.base import BackendConfigGenerator
from agentbox.core.config_generation.prompt_composer import PromptComposer

if TYPE_CHECKING:
    from agentbox.core.config_generation.run_configurator import ComposedMetadata
    from agentbox.core.data.manifest import AgentDef


class TokenConfigGenerator(BackendConfigGenerator):
    def generate(
        self,
        backend_dir: Path,
        agent: AgentDef,
        composed: ComposedMetadata,
        mcp: McpConfig | None = None,
    ) -> None:
        self._write_prompt_txt(backend_dir, composed)
        self._write_schema_json(backend_dir, composed)

    def _write_prompt_txt(self, backend_dir: Path, composed: ComposedMetadata) -> None:
        """Write a flat prompt with everything inlined."""
        prompt_txt = backend_dir / "prompt.txt"
        if prompt_txt.exists():
            return

        # Start with the shared full prompt.
        full_prompt = PromptComposer.assemble_full_prompt(composed)
        parts = [full_prompt]

        # Inline skills if present in the shared prompts directory.
        skills_md = self._read_skills_from_prompts_dir(backend_dir)
        if skills_md:
            parts.extend(["", "# Skills", skills_md])

        prompt_txt.write_text("\n\n".join(parts), encoding="utf-8")

    def _write_schema_json(self, backend_dir: Path, composed: ComposedMetadata) -> None:
        """Write schema.json copy."""
        if composed.schema is None:
            return
        schema_json = backend_dir / "schema.json"
        if schema_json.exists():
            return
        schema_json.write_text(json.dumps(composed.schema, indent=2), encoding="utf-8")

    def _read_skills_from_prompts_dir(self, backend_dir: Path) -> str:
        """Read skills.md from the shared prompts directory if it exists."""
        prompts_dir = backend_dir.parent.parent / "prompts"
        skills_md = prompts_dir / "skills.md"
        if skills_md.exists():
            return skills_md.read_text(encoding="utf-8")
        return ""
