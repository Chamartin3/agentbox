"""Tests for the runner-backends descriptor endpoint.

Asserts:
- list_runner_backends() returns the Pi backend with ``universal=True``.
- Pi's ``compatible_providers`` includes every API-key provider
  (``requires_api_key=True``) and excludes CLI-only providers
  (``requires_api_key=False``).
- A non-universal backend restricts ``compatible_providers`` to
  providers whose ``compatible_backends`` list it.
- ``supports_mcp=False`` and ``native_tools`` are correctly populated
  for MCP-incapable backends (pi, codex); MCP-capable backends default
  to ``supports_mcp=True`` and empty ``native_tools``.
"""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import MagicMock

from agentbox.api.engines.backends import list_runner_backends
from agentbox.core.data import CanonicalTool
from agentbox.core.engines.backends.base import BackendAdapter
from agentbox.core.engines.providers.base import ProviderDescriptor


# ---------------------------------------------------------------------------
# Stub providers
# ---------------------------------------------------------------------------

def _make_provider(
    id: str,
    requires_api_key: bool,
    compatible_backends: list[str] | None = None,
) -> ProviderDescriptor:
    return ProviderDescriptor(
        id=id,
        label=id.capitalize(),
        compatible_backends=compatible_backends or [],
        requires_api_key=requires_api_key,
        supports_base_url=False,
        supports_model_listing=False,
    )


# API-key providers (should appear for Pi)
_OPENAI = _make_provider("openai", requires_api_key=True, compatible_backends=["token", "pi"])
_ANTHROPIC = _make_provider("anthropic", requires_api_key=True, compatible_backends=["pi"])
_XAI = _make_provider("xai", requires_api_key=True, compatible_backends=["pi"])

# CLI-only providers (must NOT appear for Pi)
_CODEX = _make_provider("codex", requires_api_key=False, compatible_backends=["codex"])
_OLLAMA = _make_provider("ollama", requires_api_key=False, compatible_backends=["token", "opencode"])
_OPENROUTER = _make_provider("openrouter", requires_api_key=False, compatible_backends=["token"])

ALL_PROVIDERS = [_OPENAI, _ANTHROPIC, _XAI, _CODEX, _OLLAMA, _OPENROUTER]
API_KEY_PROVIDER_IDS = {"openai", "anthropic", "xai"}
CLI_ONLY_PROVIDER_IDS = {"codex", "ollama", "openrouter"}


# ---------------------------------------------------------------------------
# Stub backends
# ---------------------------------------------------------------------------

_PI_NATIVE: dict[CanonicalTool, str] = {
    CanonicalTool.FS_READ: "read",
    CanonicalTool.SHELL_EXEC: "bash",
    CanonicalTool.FS_EDIT: "edit",
    CanonicalTool.FS_WRITE: "write",
    CanonicalTool.FS_GREP: "grep",
    CanonicalTool.FS_GLOB: "find",
    CanonicalTool.FS_LIST: "ls",
}

_PI_NATIVE_CANONICAL = {k.value for k in _PI_NATIVE}


class _PiStub(BackendAdapter):
    """Minimal Pi-like backend with universal_provider = True and no MCP."""

    universal_provider: ClassVar[bool] = True
    supports_mcp: ClassVar[bool] = False
    default_model: ClassVar[str | None] = "gpt-4o"
    NATIVE_TOOLS = _PI_NATIVE

    async def run(self, *args, **kwargs):  # type: ignore[override]
        raise NotImplementedError

    def render(self, *args, **kwargs):  # type: ignore[override]
        raise NotImplementedError


class _CodexStub(BackendAdapter):
    """Minimal non-universal backend — restricted to its own provider, no MCP."""

    universal_provider: ClassVar[bool] = False
    supports_mcp: ClassVar[bool] = False
    default_model: ClassVar[str | None] = None

    async def run(self, *args, **kwargs):  # type: ignore[override]
        raise NotImplementedError

    def render(self, *args, **kwargs):  # type: ignore[override]
        raise NotImplementedError


class _ClaudeStub(BackendAdapter):
    """MCP-capable backend — should have supports_mcp=True and no native_tools."""

    universal_provider: ClassVar[bool] = False

    async def run(self, *args, **kwargs):  # type: ignore[override]
        raise NotImplementedError

    def render(self, *args, **kwargs):  # type: ignore[override]
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(backends: dict[str, type[BackendAdapter]]) -> MagicMock:
    ctx = MagicMock()
    ctx.engines.list_providers.return_value = ALL_PROVIDERS
    ctx.engines.backends.return_value = backends
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestListRunnerBackendsUniversalScope:
    """Pi universal backend is scoped to API-key providers only."""

    def test_pi_backend_is_marked_universal(self) -> None:
        ctx = _make_ctx({"pi": _PiStub})
        result = list_runner_backends(ctx=ctx)

        assert len(result) == 1
        pi = result[0]
        assert pi.id == "pi"
        assert pi.universal is True

    def test_pi_compatible_providers_includes_api_key_providers(self) -> None:
        ctx = _make_ctx({"pi": _PiStub})
        result = list_runner_backends(ctx=ctx)

        pi = result[0]
        assert set(pi.compatible_providers) == API_KEY_PROVIDER_IDS

    def test_pi_compatible_providers_excludes_cli_only_providers(self) -> None:
        ctx = _make_ctx({"pi": _PiStub})
        result = list_runner_backends(ctx=ctx)

        pi = result[0]
        for cli_id in CLI_ONLY_PROVIDER_IDS:
            assert cli_id not in pi.compatible_providers, (
                f"CLI-only provider '{cli_id}' must not appear in Pi's compatible_providers"
            )

    def test_pi_excludes_ollama(self) -> None:
        """Ollama has requires_api_key=False and must not appear for Pi."""
        ctx = _make_ctx({"pi": _PiStub})
        result = list_runner_backends(ctx=ctx)

        pi = result[0]
        assert "ollama" not in pi.compatible_providers

    def test_pi_excludes_codex(self) -> None:
        """Codex CLI has requires_api_key=False and must not appear for Pi."""
        ctx = _make_ctx({"pi": _PiStub})
        result = list_runner_backends(ctx=ctx)

        pi = result[0]
        assert "codex" not in pi.compatible_providers

    def test_pi_excludes_openrouter(self) -> None:
        """openrouter has requires_api_key=False and must not appear for Pi."""
        ctx = _make_ctx({"pi": _PiStub})
        result = list_runner_backends(ctx=ctx)

        pi = result[0]
        assert "openrouter" not in pi.compatible_providers


class TestListRunnerBackendsNonUniversal:
    """Non-universal backends restrict compatible_providers to declared compat list."""

    def test_codex_only_sees_its_own_providers(self) -> None:
        ctx = _make_ctx({"codex": _CodexStub})
        result = list_runner_backends(ctx=ctx)

        assert len(result) == 1
        codex = result[0]
        assert codex.id == "codex"
        assert codex.universal is False
        # Only codex has "codex" in compatible_backends
        assert codex.compatible_providers == ["codex"]

    def test_non_universal_excludes_api_key_only_providers(self) -> None:
        """Providers that do not list 'codex' in compatible_backends are excluded."""
        ctx = _make_ctx({"codex": _CodexStub})
        result = list_runner_backends(ctx=ctx)

        codex = result[0]
        for api_id in ("openai", "anthropic", "xai"):
            assert api_id not in codex.compatible_providers


class TestListRunnerBackendsMixed:
    """Mixed backend registry returns correct per-backend scoping."""

    def test_mixed_pi_and_codex(self) -> None:
        ctx = _make_ctx({"codex": _CodexStub, "pi": _PiStub})
        result = list_runner_backends(ctx=ctx)

        by_id = {d.id: d for d in result}
        assert set(by_id) == {"codex", "pi"}

        # Pi: only API-key providers
        assert set(by_id["pi"].compatible_providers) == API_KEY_PROVIDER_IDS
        assert by_id["pi"].universal is True

        # Codex: only its own provider
        assert by_id["codex"].compatible_providers == ["codex"]
        assert by_id["codex"].universal is False


class TestBackendDescriptorSupportsMcp:
    """supports_mcp and native_tools fields on BackendDescriptor."""

    def test_pi_has_supports_mcp_false(self) -> None:
        ctx = _make_ctx({"pi": _PiStub})
        result = list_runner_backends(ctx=ctx)

        pi = result[0]
        assert pi.supports_mcp is False

    def test_pi_native_tools_matches_canonical_values(self) -> None:
        ctx = _make_ctx({"pi": _PiStub})
        result = list_runner_backends(ctx=ctx)

        pi = result[0]
        assert set(pi.native_tools) == _PI_NATIVE_CANONICAL

    def test_pi_native_tools_expected_set(self) -> None:
        ctx = _make_ctx({"pi": _PiStub})
        result = list_runner_backends(ctx=ctx)

        pi = result[0]
        assert set(pi.native_tools) == {
            "fs.read", "shell.exec", "fs.edit", "fs.write", "fs.grep", "fs.glob", "fs.list"
        }

    def test_codex_has_supports_mcp_false(self) -> None:
        ctx = _make_ctx({"codex": _CodexStub})
        result = list_runner_backends(ctx=ctx)

        codex = result[0]
        assert codex.supports_mcp is False

    def test_mcp_capable_backend_defaults_supports_mcp_true(self) -> None:
        ctx = _make_ctx({"claude": _ClaudeStub})
        result = list_runner_backends(ctx=ctx)

        claude = result[0]
        assert claude.supports_mcp is True

    def test_mcp_capable_backend_has_empty_native_tools(self) -> None:
        ctx = _make_ctx({"claude": _ClaudeStub})
        result = list_runner_backends(ctx=ctx)

        claude = result[0]
        assert claude.native_tools == []

    def test_real_pi_backend_supports_mcp_false(self) -> None:
        """The actual PiBackend class must advertise supports_mcp=False."""
        from agentbox.core.engines.backends.pi.adapter import PiBackend

        assert PiBackend.supports_mcp is False

    def test_real_pi_backend_native_tools_correct(self) -> None:
        """The actual PiBackend.NATIVE_TOOLS must match the pi/tools module."""
        from agentbox.core.engines.backends.pi.adapter import PiBackend
        from agentbox.core.engines.backends.pi.tools import NATIVE_TOOLS

        assert PiBackend.NATIVE_TOOLS is NATIVE_TOOLS

    def test_real_pi_backend_descriptor_native_tools(self) -> None:
        """list_runner_backends with real PiBackend reports the 7 pi native tools."""
        from agentbox.core.engines.backends.pi.adapter import PiBackend

        ctx = _make_ctx({"pi": PiBackend})
        result = list_runner_backends(ctx=ctx)

        pi = result[0]
        assert set(pi.native_tools) == {
            "fs.read", "shell.exec", "fs.edit", "fs.write", "fs.grep", "fs.glob", "fs.list"
        }
