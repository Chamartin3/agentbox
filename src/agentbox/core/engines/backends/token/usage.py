"""Usage extraction helper for ``TokenBackend``.

pydantic-ai has shipped two different surfaces for run-time token
accounting: the older shape exposed ``request_tokens`` /
``response_tokens`` on a usage object, the 1.x shape exposes
``input_tokens`` / ``output_tokens``. Some versions return usage as a
callable (``result.usage()``); others as an attribute. We normalise
both shapes into a flat ``(input_tokens, output_tokens, model)``
tuple so the backend's ``UsageEvent`` emission stays trivial.
"""

from __future__ import annotations

from typing import Any


def extract_usage(result: Any) -> tuple[int, int, str | None]:
    """Return ``(input_tokens, output_tokens, model_name)`` from a result.

    Falls back to ``(0, 0, None)`` when no usage info is available
    (provider returned nothing, or the call raised before usage was
    recorded).
    """
    raw_usage = getattr(result, "usage", None)
    if callable(raw_usage):
        try:
            raw_usage = raw_usage()
        except Exception:
            raw_usage = None
    if raw_usage is None:
        return 0, 0, None
    input_tokens = (
        getattr(raw_usage, "input_tokens", None)
        or getattr(raw_usage, "request_tokens", None)
        or 0
    )
    output_tokens = (
        getattr(raw_usage, "output_tokens", None)
        or getattr(raw_usage, "response_tokens", None)
        or 0
    )
    model_name = getattr(raw_usage, "model", None)
    return input_tokens, output_tokens, model_name
