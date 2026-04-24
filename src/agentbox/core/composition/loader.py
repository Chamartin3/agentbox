"""Bundle loader — turns an agent directory into a typed ``Bundle``.

Validates file existence at load time so missing references are caught
early, before the runner is invoked.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from pathlib import Path

from agentbox.core.composition import ComposeResult, compose
from agentbox.core.data.manifest import CompositionConfig

logger = logging.getLogger(__name__)


@dataclass
class Bundle:
    """Self-contained agent bundle ready for composition."""

    agent_id: str
    path: Path
    composition: CompositionConfig
    legacy_prompt_path: str | None = None
    """Populated when the source uses the legacy ``prompt_path`` field
    and has no ``[composition]`` block."""

    def compose(
        self,
        variables: dict[str, str],
        shared_roots: dict[str, Path] | None = None,
    ) -> ComposeResult:
        return compose(self.path, variables, shared_roots or {})


def load_bundle(
    agent_id: str,
    root: Path,
    manifest_composition: CompositionConfig | None = None,
    legacy_prompt_path: str | None = None,
) -> Bundle:
    """Load an agent bundle from ``root`` (the agent directory).

    Args:
        agent_id: stable agent identifier.
        root: directory containing ``agent.toml``, ``prompts/``, etc.
        manifest_composition: ``CompositionConfig`` already parsed from
            ``agent.toml`` (optional — when ``None``, the file is read again).
        legacy_prompt_path: legacy top-level ``prompt_path`` for fallback.

    Returns:
        A ``Bundle`` with validated file existence.

    Raises:
        FileNotFoundError: if the bundle directory or a declared file is missing.
    """
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"bundle directory not found: {root}")

    toml_path = root / "agent.toml"
    if toml_path.exists():
        import tomllib

        with toml_path.open("rb") as f:
            data = tomllib.load(f)
        raw_composition = data.get("composition")
        if raw_composition is not None:
            composition = CompositionConfig.model_validate(raw_composition)
        else:
            composition = None
    else:
        composition = None

    # Manifest composition wins over re-reading the file (inline agents).
    if manifest_composition is not None:
        composition = manifest_composition

    if composition is None:
        # Legacy fallback: synthesise a minimal composition from prompt_path.
        if legacy_prompt_path:
            warnings.warn(
                f"Agent {agent_id!r} uses legacy prompt_path without [composition]. "
                "Migrate to [composition] block.",
                DeprecationWarning,
                stacklevel=2,
            )
            resolved = (
                (root / legacy_prompt_path).resolve()
                if not Path(legacy_prompt_path).is_absolute()
                else Path(legacy_prompt_path)
            )
            if resolved.exists():
                try:
                    rel = resolved.relative_to(root)
                except ValueError:
                    rel = Path(legacy_prompt_path)
                composition = CompositionConfig(system=str(rel))
            else:
                composition = CompositionConfig(system=legacy_prompt_path)
        else:
            # Absolute fallback — look for prompts/system.md
            default = root / "prompts" / "system.md"
            if default.exists():
                composition = CompositionConfig()
            else:
                raise FileNotFoundError(
                    f"bundle {root} has no [composition] block and no prompts/system.md"
                )

    # Validate declared files exist (bundle-relative refs only)
    system_path = root / composition.system
    if not system_path.exists():
        raise FileNotFoundError(f"bundle system prompt missing: {system_path}")

    for ref in composition.references:
        path_str = ref if isinstance(ref, str) else ref["path"]
        if not path_str.startswith("shared://"):
            ref_path = root / path_str
            if not ref_path.exists():
                raise FileNotFoundError(f"bundle reference missing: {ref_path}")

    if composition.user_template:
        ut_path = root / composition.user_template
        if not ut_path.exists():
            raise FileNotFoundError(f"bundle user_template missing: {ut_path}")

    if composition.output_schema:
        schema_path = root / composition.output_schema
        if not schema_path.exists():
            raise FileNotFoundError(f"bundle output_schema missing: {schema_path}")

    return Bundle(
        agent_id=agent_id,
        path=root,
        composition=composition,
        legacy_prompt_path=legacy_prompt_path if composition is None else None,
    )
