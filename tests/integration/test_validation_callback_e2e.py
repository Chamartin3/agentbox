"""E2E smoke tests for the two-gate validation architecture.

Companion to ``docs/plans/validation-callback-architecture.md`` and
``docs/plans/validation-smoke-test-ollama.md``.

Requires:
  - Ollama running with llama3.2:1b available (``OLLAMA_HOST`` set)
  - consumer Django reachable at ``CVMAN_BASE_URL`` (default: http://consumer Django:8000)
  - ``test.structured_output`` agent seeded (``push_agent_schemas.py test.structured_output``)

Run:
    docker compose --profile verify up -d ollama ollama-seed
    ./dev.sh up
    OLLAMA_HOST=http://localhost:11434 \\
      uv run pytest -m "live_ollama and live_callback" tests/integration/test_validation_callback_e2e.py -v

Markers:
  live_ollama   — requires OLLAMA_HOST env var
  live_callback — requires CVMAN_BASE_URL to be reachable
"""

from __future__ import annotations

import os

import httpx
import pytest

pytestmark = [
    pytest.mark.live_ollama,
    pytest.mark.live_callback,
]

CVMAN_BASE_URL = os.environ.get("CVMAN_BASE_URL", "http://localhost:8086")
AGENT_ID = "test.structured_output"
USER_MSG = (
    "Write a JSON record about an imaginary internal tool called 'CitrusBoard'. "
    "Include a short title, 3 bullets covering what it does, who uses it, and why "
    "it was built, and a one-paragraph summary."
)
USER_MSG_TERSE = (
    "Write a very brief record. Keep the summary to one sentence and the bullets "
    "to a few words each."
)


def _validator_reachable() -> bool:
    try:
        r = httpx.get(f"{CVMAN_BASE_URL}/health/", timeout=3)
        return r.status_code < 500
    except Exception:
        return False


@pytest.fixture(autouse=True)
def require_callback(request):
    if not _validator_reachable():
        pytest.skip(f"consumer Django not reachable at {CVMAN_BASE_URL}")


class TestValidationCallbackGateUnit:
    """Unit-level tests for the Django Gate-2 endpoint — no agentbox needed."""

    def test_valid_output_passes(self):
        payload = {
            "output": (
                '{"title": "CitrusBoard Dashboard", '
                '"bullets": ["Manages project tasks", "Used by product teams", "Built to replace spreadsheets"], '
                '"summary": "CitrusBoard is an internal project management tool that gives teams real-time visibility into their work."}'
            )
        }
        r = httpx.post(
            f"{CVMAN_BASE_URL}/api/agent-validation/{AGENT_ID}/",
            json=payload,
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True

    def test_structural_failure_caught(self):
        # Only one bullet — violates minItems=2
        payload = {
            "output": (
                '{"title": "Citrus", '
                '"bullets": ["Just one bullet"], '
                '"summary": "A reasonably long summary that has enough characters to avoid the aggregate validator."}'
            )
        }
        r = httpx.post(
            f"{CVMAN_BASE_URL}/api/agent-validation/{AGENT_ID}/",
            json=payload,
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        # This structural issue (minItems) IS expressible in JSON Schema → Gate 1 would
        # catch it, but Gate 2 also catches it since Pydantic enforces it.
        assert data["ok"] is False
        assert "bullet" in data["error"].lower() or "min" in data["error"].lower()

    def test_aggregate_failure_caught(self):
        # Passes per-field constraints but total length < 150 chars
        payload = {
            "output": (
                '{"title": "Board", '
                '"bullets": ["does stuff", "is useful"], '
                '"summary": "A short summary."}'
            )
        }
        r = httpx.post(
            f"{CVMAN_BASE_URL}/api/agent-validation/{AGENT_ID}/",
            json=payload,
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert "150" in data["error"] or "too short" in data["error"].lower()

    def test_unknown_agent_returns_404(self):
        payload = {"output": '{"x": 1}'}
        r = httpx.post(
            f"{CVMAN_BASE_URL}/api/agent-validation/nonexistent.agent/",
            json=payload,
            timeout=10,
        )
        assert r.status_code == 404

    def test_fenced_json_is_extracted(self):
        # Output wrapped in markdown fence — should still validate
        fenced = (
            "```json\n"
            '{"title": "CitrusBoard Dashboard", '
            '"bullets": ["Manages project tasks", "Used by product teams", "Built to replace spreadsheets"], '
            '"summary": "CitrusBoard is an internal project management tool that gives teams real-time visibility."}'
            "\n```"
        )
        payload = {"output": fenced}
        r = httpx.post(
            f"{CVMAN_BASE_URL}/api/agent-validation/{AGENT_ID}/",
            json=payload,
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True
