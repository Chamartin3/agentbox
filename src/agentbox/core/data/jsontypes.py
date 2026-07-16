"""The ONE sanctioned type for genuinely-arbitrary JSON at a true boundary.

``RawJson`` / ``RawJsonValue`` are the *only* permitted representation of JSON
whose shape is genuinely open — and ONLY at real boundaries:

- data our code just forwards without inspecting (a run's backend-emitted
  transcript events, a JSON Schema like ``inputSchema``, a provider
  ``extra_body`` passthrough),
- the raw output of ``json.loads`` at a parse site, immediately narrowed into a
  concrete type.

They are NOT a general dict alias. If you know the shape, use a ``TypedDict`` /
dataclass / pydantic model — reaching for ``RawJson`` on a known shape is the
same cheat as ``dict[str, Any]`` with a nicer name, and reviewers should reject
it. The name is deliberately loud so its ~dozen legitimate uses stay greppable
and every other use stands out as debt.

Stdlib-only, so ``core.data`` stays the dependency-graph leaf.
"""

from __future__ import annotations

type RawJsonValue = str | int | float | bool | None | dict[str, RawJsonValue] | list[RawJsonValue]
"""Any JSON-serializable value at a genuinely-open boundary."""

type RawJson = dict[str, RawJsonValue]
"""A JSON object at a genuinely-open boundary (forwarded or about-to-be-parsed)."""
