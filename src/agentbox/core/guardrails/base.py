"""Guardrail abstract base.

Guardrails run after all retry attempts complete (success or failure).
They evaluate the final output and emit a ``GuardrailEvent`` that is
recorded in telemetry and surfaced to the caller.

Guardrails are observational — they do NOT trigger retries. Output
validation retries are driven by ``RunnerSpec.max_validation_retries``
and the ``output_schema_path`` JSON Schema check, which run before
guardrails.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class GuardrailResult:
    ok: bool
    message: str | None = None
    """Feedback shown to the user and (on retry) appended to next prompt."""


@dataclass
class GuardrailContext:
    run_id: str
    agent_id: str
    input: str
    output: str
    """Final assistant text or JSON payload extracted from the runner output."""

    transcript_path: str
    """Path to the JSONL transcript on disk."""

    attempt: int = 0
    options: dict | None = None


class Guardrail(ABC):
    name: str = "abstract"

    @abstractmethod
    def evaluate(self, ctx: GuardrailContext) -> GuardrailResult: ...
