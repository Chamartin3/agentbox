"""Prompt composition — shared bundle renderer for agentbox and callers.

This module is intentionally HTTP-free and side-effect-free so that caller
projects can import it without pulling in the agentbox server
runtime.

"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_TEMPLATE_VAR_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _format_template(text: str, variables: dict[str, str]) -> str:
    """Substitute ``{var_name}`` placeholders only.

    Unlike ``str.format``, this leaves every other brace untouched — so
    prompts can embed literal JSON examples (``{"key": value}``) without
    needing them escaped as ``{{ }}``. Only bare identifier placeholders
    matching a known variable key are replaced; unknown ``{name}`` tokens
    are passed through verbatim.
    """
    missing: list[str] = []

    def _sub(m: re.Match[str]) -> str:
        key = m.group(1)
        if key in variables:
            return str(variables[key])
        missing.append(key)
        return m.group(0)

    rendered = _TEMPLATE_VAR_RE.sub(_sub, text)
    if missing:
        raise KeyError(f"Missing template variable {missing[0]!r} in prompt")
    return rendered


def _ref_heading_fallback(path: str) -> str:
    if path.startswith("shared://"):
        tail = path[len("shared://") :].rsplit("/", 1)[-1]
    else:
        tail = path.rsplit("/", 1)[-1]
    stem, _, _ = tail.partition(".")
    return stem or tail

