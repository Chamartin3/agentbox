"""Tests for tool discovery via entry points."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

from agentbox.core.tools import registry
from agentbox.core.tools.registry import discover_tools


class TestDiscoverTools:
    def test_idempotent_on_second_call(self) -> None:
        registry._DISCOVERED = False
        with patch("agentbox.core.tools.registry.entry_points") as mock_eps:
            mock_eps.return_value = []
            discover_tools()
            discover_tools()
            assert mock_eps.call_count == 1

    def test_force_rediscovery(self) -> None:
        registry._DISCOVERED = False
        with patch("agentbox.core.tools.registry.entry_points") as mock_eps:
            mock_eps.return_value = []
            discover_tools()
            discover_tools(force=True)
            assert mock_eps.call_count == 2

    def test_loads_entry_points(self) -> None:
        registry._DISCOVERED = False
        fake_ep = MagicMock()
        fake_ep.name = "my_tool"
        fake_ep.value = "my.module:func"

        with patch("agentbox.core.tools.registry.entry_points") as mock_eps:
            mock_eps.return_value = [fake_ep]
            discover_tools(force=True)
            fake_ep.load.assert_called_once()

    def test_skips_broken_entry_point(self) -> None:
        registry._DISCOVERED = False
        fake_ep = MagicMock()
        fake_ep.name = "bad_tool"
        fake_ep.value = "bad.module"
        fake_ep.load.side_effect = ImportError("no module")

        with patch("agentbox.core.tools.registry.entry_points") as mock_eps:
            mock_eps.return_value = [fake_ep]
            discover_tools(force=True)
