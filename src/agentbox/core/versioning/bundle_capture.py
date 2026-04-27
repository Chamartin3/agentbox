"""Capture a full bundle (system + user_template + references + output_schema)
into the row shape expected by ``agent_version_files``.

This is the import-side half of DB-as-source-of-truth: it walks the
composition declared in an :class:`AgentDef`, reads every file from disk
(including ``shared://`` references resolved via ``shared_roots``), and
returns a list of dicts ready to hand to
``SessionStore.create_version(..., files=...)``.

Failures to read a referenced file are surfaced as ``FileNotFoundError``
so the caller can decide whether to skip the import or log and continue —
silently dropping references would let a broken bundle land in the DB
unnoticed, which is exactly the failure mode this whole refactor exists
to prevent.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentbox.core.data.manifest import AgentDef, CompositionConfig

logger = logging.getLogger(__name__)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _bundle_root(agent: AgentDef, project_root: Path) -> Path | None:
    """Locate the on-disk bundle directory for ``agent``.

    Bundle agents store all referenced files relative to the directory
    holding ``agent.toml``. Inline / markdown agents have no bundle dir.
    """
    if agent.source_path is None:
        return None
    src = Path(agent.source_path)
    if src.is_dir():
        return src
    if src.name == "agent.toml":
        return src.parent
    return None


def _resolve_reference(
    ref_path: str,
    bundle_root: Path | None,
    shared_roots: dict[str, Path],
) -> Path | None:
    if ref_path.startswith("shared://"):
        rest = ref_path[len("shared://") :]
        key, _, rel = rest.partition("/")
        root = shared_roots.get(key)
        if root is None:
            return None
        return root / rel
    if bundle_root is None:
        return None
    return bundle_root / ref_path


def capture_bundle_files(
    agent: AgentDef,
    project_root: Path,
    shared_roots: dict[str, Path],
) -> list[dict]:
    """Snapshot every file the bundle composition consumes.

    Returns rows shaped for ``agent_version_files``:
    ``{kind, relative_path, source_uri, content, sha256, position}``.

    Returns an empty list when the agent has no composition and no
    ``prompt_path`` — there is nothing to capture in that case.
    """
    rows: list[dict] = []
    bundle_root = _bundle_root(agent, project_root)
    composition: CompositionConfig | None = agent.composition

    # -- system prompt -------------------------------------------------
    sys_rel: str | None = None
    sys_text: str | None = None
    if composition is not None:
        sys_rel = composition.system
        sys_path = (bundle_root / sys_rel) if bundle_root is not None else None
        if sys_path is not None and sys_path.exists():
            sys_text = _read_text(sys_path)
        elif agent.prompt:
            sys_text = agent.prompt
    elif agent.prompt_path:
        sys_rel = agent.prompt_path
        candidate = project_root / agent.prompt_path
        if candidate.exists():
            sys_text = _read_text(candidate)
        elif agent.prompt:
            sys_text = agent.prompt
    elif agent.prompt:
        sys_rel = "prompts/system.md"
        sys_text = agent.prompt

    if sys_rel is not None and sys_text is not None:
        rows.append(
            {
                "kind": "system",
                "relative_path": sys_rel,
                "content": sys_text,
                "sha256": _sha256(sys_text),
                "source_uri": None,
                "position": 0,
            }
        )

    if composition is None:
        return rows

    # -- user_template -------------------------------------------------
    if composition.user_template and bundle_root is not None:
        ut_path = bundle_root / composition.user_template
        if ut_path.exists():
            text = _read_text(ut_path)
            rows.append(
                {
                    "kind": "user_template",
                    "relative_path": composition.user_template,
                    "content": text,
                    "sha256": _sha256(text),
                    "source_uri": None,
                    "position": 0,
                }
            )
        else:
            raise FileNotFoundError(
                f"user_template declared but missing: {ut_path}"
            )

    # -- references ----------------------------------------------------
    for i, ref in enumerate(composition.references or []):
        if isinstance(ref, dict):
            ref_path = ref.get("path")
            if not isinstance(ref_path, str):
                raise ValueError(f"reference entry missing 'path': {ref!r}")
        else:
            ref_path = str(ref)
        resolved = _resolve_reference(ref_path, bundle_root, shared_roots)
        if resolved is None or not resolved.exists():
            raise FileNotFoundError(
                f"reference {ref_path!r} not found (resolved={resolved})"
            )
        text = _read_text(resolved)
        rows.append(
            {
                "kind": "reference",
                "relative_path": ref_path,
                "content": text,
                "sha256": _sha256(text),
                "source_uri": ref_path if ref_path.startswith("shared://") else None,
                "position": i,
            }
        )

    # -- output_schema -------------------------------------------------
    if composition.output_schema and bundle_root is not None:
        schema_path = bundle_root / composition.output_schema
        if not schema_path.exists():
            raise FileNotFoundError(
                f"output_schema declared but missing: {schema_path}"
            )
        raw = _read_text(schema_path)
        # Re-serialise without sort_keys so the parsed dict keeps insertion
        # order — matches the FilesystemBundleSource snapshot semantics.
        try:
            parsed = json.loads(raw)
            content = json.dumps(parsed)
        except json.JSONDecodeError:
            content = raw
        rows.append(
            {
                "kind": "output_schema",
                "relative_path": composition.output_schema,
                "content": content,
                "sha256": _sha256(content),
                "source_uri": None,
                "position": 0,
            }
        )

    # -- input_schema --------------------------------------------------
    # Auto-detected from the bundle root (matches FilesystemBundleSource).
    if bundle_root is not None:
        from agentbox.core.constants import BundleFile

        input_schema_path = bundle_root / BundleFile.INPUT_SCHEMA
        if input_schema_path.exists():
            raw = _read_text(input_schema_path)
            try:
                parsed = json.loads(raw)
                content = json.dumps(parsed)
            except json.JSONDecodeError:
                content = raw
            rows.append(
                {
                    "kind": "input_schema",
                    "relative_path": BundleFile.INPUT_SCHEMA,
                    "content": content,
                    "sha256": _sha256(content),
                    "source_uri": None,
                    "position": 0,
                }
            )

    return rows
