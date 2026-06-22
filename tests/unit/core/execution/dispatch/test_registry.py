"""Unit tests for the dispatch channel registry.

Covers ``get_channel``, ``available_channels``, and the ``_load_channels``
loader from ``agentbox.core.execution.dispatch.registry``.

The ``_DISPATCH_CHANNELS`` module-level dict is patched directly via
``monkeypatch`` to avoid relying on real entry-point distribution metadata.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import agentbox.core.execution.dispatch.registry as registry_module
from agentbox.core.execution.dispatch.registry import (
    _load_channels,
    available_channels,
    get_channel,
)


# --------------------------------------------------------------------------- #
# Minimal channel stubs
# --------------------------------------------------------------------------- #


class _FakeAlphaChannel:
    name = "alpha"


class _FakeBetaChannel:
    name = "beta"


class _FakeZetaChannel:
    name = "zeta"


# --------------------------------------------------------------------------- #
# get_channel
# --------------------------------------------------------------------------- #


@pytest.mark.unit
class TestGetChannel:
    """Verify name-based channel lookup behavior."""

    def test_get_channel_returns_registered_class(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A channel class registered under a name is returned by that name."""
        # Arrange
        monkeypatch.setattr(registry_module, "_DISPATCH_CHANNELS", {"alpha": _FakeAlphaChannel})

        # Act
        result = get_channel("alpha")

        # Assert
        assert result is _FakeAlphaChannel

    def test_get_channel_raises_key_error_for_unknown_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Requesting a channel that was never registered raises KeyError."""
        # Arrange
        monkeypatch.setattr(registry_module, "_DISPATCH_CHANNELS", {})

        # Act & Assert
        with pytest.raises(KeyError, match="no dispatch channel registered"):
            get_channel("nonexistent")

    def test_get_channel_error_message_includes_channel_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The KeyError message names the unregistered channel so the caller can diagnose."""
        # Arrange
        monkeypatch.setattr(registry_module, "_DISPATCH_CHANNELS", {})

        # Act & Assert
        with pytest.raises(KeyError, match="ghost_channel"):
            get_channel("ghost_channel")


# --------------------------------------------------------------------------- #
# available_channels
# --------------------------------------------------------------------------- #


@pytest.mark.unit
class TestAvailableChannels:
    """Verify that the channel name listing is sorted and complete."""

    def test_returns_sorted_channel_names(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Channel names are returned in ascending lexicographic order."""
        # Arrange — deliberately insert in reverse order to test sorting
        monkeypatch.setattr(
            registry_module,
            "_DISPATCH_CHANNELS",
            {"zeta": _FakeZetaChannel, "alpha": _FakeAlphaChannel, "beta": _FakeBetaChannel},
        )

        # Act
        result = available_channels()

        # Assert
        assert result == ["alpha", "beta", "zeta"]

    def test_returns_empty_list_when_no_channels_registered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty registry produces an empty list, not an error."""
        # Arrange
        monkeypatch.setattr(registry_module, "_DISPATCH_CHANNELS", {})

        # Act
        result = available_channels()

        # Assert
        assert result == []

    def test_returns_list_not_dict_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The return type is a plain list, not a dict_keys view."""
        # Arrange
        monkeypatch.setattr(
            registry_module, "_DISPATCH_CHANNELS", {"alpha": _FakeAlphaChannel}
        )

        # Act
        result = available_channels()

        # Assert
        assert isinstance(result, list)


# --------------------------------------------------------------------------- #
# _load_channels — entry-point loading behavior
# --------------------------------------------------------------------------- #


@pytest.mark.unit
class TestLoadChannels:
    """Verify the loader handles broken/malformed entry points gracefully."""

    def test_entry_point_with_valid_name_classvar_is_registered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A well-formed channel class with a string `name` is added to the registry."""
        # Arrange
        ep = MagicMock()
        ep.load.return_value = _FakeAlphaChannel
        ep.name = "alpha_ep"
        monkeypatch.setattr(registry_module, "entry_points", lambda group: [ep])

        # Act
        result = _load_channels()

        # Assert
        assert result == {"alpha": _FakeAlphaChannel}

    def test_entry_point_without_name_classvar_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A channel class that has no `name` ClassVar is skipped without raising."""
        # Arrange
        class _NoNameChannel:
            pass  # deliberately omits the `name` ClassVar

        ep = MagicMock()
        ep.load.return_value = _NoNameChannel
        ep.name = "bad_ep"
        monkeypatch.setattr(registry_module, "entry_points", lambda group: [ep])

        # Act
        result = _load_channels()
        captured = capsys.readouterr()

        # Assert — channel is absent and a warning was printed
        assert result == {}
        assert "no 'name' ClassVar" in captured.out

    def test_entry_point_with_empty_name_classvar_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A channel class with an empty string `name` is skipped (falsy check)."""
        # Arrange
        class _EmptyNameChannel:
            name = ""

        ep = MagicMock()
        ep.load.return_value = _EmptyNameChannel
        ep.name = "empty_name_ep"
        monkeypatch.setattr(registry_module, "entry_points", lambda group: [ep])

        # Act
        result = _load_channels()

        # Assert
        assert result == {}

    def test_entry_point_load_raises_import_error_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """An entry point whose load() raises ImportError does not crash the registry."""
        # Arrange
        ep = MagicMock()
        ep.load.side_effect = ImportError("missing optional dep")
        ep.name = "broken_ep"
        monkeypatch.setattr(registry_module, "entry_points", lambda group: [ep])

        # Act
        result = _load_channels()
        captured = capsys.readouterr()

        # Assert — empty result, failure message printed, no exception
        assert result == {}
        assert "failed to load" in captured.out

    def test_entry_point_load_raises_generic_exception_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Any exception from ep.load() is caught; the entry point is skipped."""
        # Arrange
        ep = MagicMock()
        ep.load.side_effect = Exception("unexpected error")
        ep.name = "noisy_ep"
        monkeypatch.setattr(registry_module, "entry_points", lambda group: [ep])

        # Act — must not raise
        result = _load_channels()

        # Assert
        assert result == {}

    def test_duplicate_channel_name_second_entry_point_overwrites_first(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Two entry points sharing a channel name emit a warning; the later one wins."""
        # Arrange
        class _FirstChannel:
            name = "dup"

        class _SecondChannel:
            name = "dup"

        ep1 = MagicMock()
        ep1.load.return_value = _FirstChannel
        ep1.name = "ep_first"

        ep2 = MagicMock()
        ep2.load.return_value = _SecondChannel
        ep2.name = "ep_second"

        monkeypatch.setattr(registry_module, "entry_points", lambda group: [ep1, ep2])

        # Act
        result = _load_channels()
        captured = capsys.readouterr()

        # Assert — second class wins, warning is printed
        assert result["dup"] is _SecondChannel
        assert "WARNING" in captured.out
        assert "duplicate" in captured.out.lower()

    def test_multiple_valid_entry_points_all_registered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All valid entry points are registered when no errors occur."""
        # Arrange
        ep1 = MagicMock()
        ep1.load.return_value = _FakeAlphaChannel
        ep1.name = "ep_alpha"

        ep2 = MagicMock()
        ep2.load.return_value = _FakeBetaChannel
        ep2.name = "ep_beta"

        monkeypatch.setattr(registry_module, "entry_points", lambda group: [ep1, ep2])

        # Act
        result = _load_channels()

        # Assert
        assert result == {"alpha": _FakeAlphaChannel, "beta": _FakeBetaChannel}
