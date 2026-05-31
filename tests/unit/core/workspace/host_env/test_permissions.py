"""Tests for host-env grant resolution and permission checks."""

from __future__ import annotations

import pytest

from agentbox.core.workspace.host_env.permissions import (
    GrantViolation,
    _deep_merge,
    _path_within_allowlist,
    check_capability,
    resolve_grants,
)


class TestDeepMerge:
    def test_simple_override(self) -> None:
        assert _deep_merge({"a": 1}, {"a": 2}) == {"a": 2}

    def test_adds_new_keys(self) -> None:
        assert _deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

    def test_none_base(self) -> None:
        assert _deep_merge(None, {"a": 1}) == {"a": 1}

    def test_none_overrides(self) -> None:
        assert _deep_merge({"a": 1}, None) == {"a": 1}

    def test_nested_merge(self) -> None:
        base = {"fs": {"read": {"max_bytes": 100}}}
        overrides = {"fs": {"read": {"allowed_paths": ["/tmp"]}}}
        result = _deep_merge(base, overrides)
        assert result["fs"]["read"]["max_bytes"] == 100
        assert result["fs"]["read"]["allowed_paths"] == ["/tmp"]

    def test_list_replaces_not_merges(self) -> None:
        base = {"allowlist": ["a", "b"]}
        overrides = {"allowlist": ["c"]}
        assert _deep_merge(base, overrides) == {"allowlist": ["c"]}


class TestPathWithinAllowlist:
    def test_exact_match(self) -> None:
        assert _path_within_allowlist("/tmp/file.txt", ["/tmp"]) is True

    def test_subdirectory(self) -> None:
        assert _path_within_allowlist("/tmp/sub/file.txt", ["/tmp"]) is True

    def test_not_within(self) -> None:
        assert _path_within_allowlist("/etc/passwd", ["/tmp"]) is False

    def test_multiple_roots(self) -> None:
        assert _path_within_allowlist("/var/log/app.log", ["/tmp", "/var"]) is True


class TestResolveGrants:
    def test_adds_default_granted_capabilities(self) -> None:
        grants = resolve_grants({}, {})
        assert "http.fetch" in grants

    def test_merges_profile_and_overrides(self) -> None:
        grants = resolve_grants(
            {"env.get": {"allowlist": ["HOME"]}},
            {"env.get": {"allowlist": ["PATH"]}},
        )
        assert grants["env.get"]["allowlist"] == ["PATH"]

    def test_keeps_profile_grants_without_overrides(self) -> None:
        grants = resolve_grants({"env.get": {"allowlist": ["HOME"]}}, None)
        assert grants["env.get"]["allowlist"] == ["HOME"]


class TestCheckCapability:
    def test_unknown_capability_raises(self) -> None:
        with pytest.raises(GrantViolation, match="unknown capability"):
            check_capability({}, "no.such.capability")

    def test_not_granted_raises(self) -> None:
        with pytest.raises(GrantViolation, match="not granted"):
            check_capability({}, "env.get")

    def test_env_get_valid(self) -> None:
        grants = {"env.get": {"allowlist": ["HOME"]}}
        check_capability(grants, "env.get", {"name": "HOME"})

    def test_env_get_not_allowlisted(self) -> None:
        grants = {"env.get": {"allowlist": ["HOME"]}}
        with pytest.raises(GrantViolation, match="not allowlisted"):
            check_capability(grants, "env.get", {"name": "SECRET"})

    def test_env_get_missing_name(self) -> None:
        grants = {"env.get": {"allowlist": ["HOME"]}}
        with pytest.raises(GrantViolation, match="missing .* name"):
            check_capability(grants, "env.get", {})

    def test_fs_read_valid_path(self) -> None:
        grants = {"fs.read": {"allowed_paths": ["/tmp"]}}
        check_capability(grants, "fs.read", {"path": "/tmp/file.txt"})

    def test_fs_read_not_in_paths(self) -> None:
        grants = {"fs.read": {"allowed_paths": ["/tmp"]}}
        with pytest.raises(GrantViolation, match="not within"):
            check_capability(grants, "fs.read", {"path": "/etc/passwd"})

    def test_fs_read_no_allowed_paths(self) -> None:
        grants = {"fs.read": {}}
        with pytest.raises(GrantViolation, match="no allowed_paths"):
            check_capability(grants, "fs.read", {"path": "/tmp/x"})

    def test_fs_read_size_exceeds_max(self) -> None:
        grants = {"fs.read": {"allowed_paths": ["/tmp"], "max_bytes": 100}}
        with pytest.raises(GrantViolation, match="exceeds max_bytes"):
            check_capability(grants, "fs.read", {"path": "/tmp/x", "size_hint": 200})

    def test_shell_exec_valid(self) -> None:
        grants = {"shell.exec": {"command_allowlist": ["echo .*"]}}
        check_capability(grants, "shell.exec", {"cmd": "echo hello"})

    def test_shell_exec_not_allowed(self) -> None:
        grants = {"shell.exec": {"command_allowlist": ["echo .*"]}}
        with pytest.raises(GrantViolation, match="not on allowlist"):
            check_capability(grants, "shell.exec", {"cmd": "rm -rf /"})

    def test_shell_exec_no_allowlist(self) -> None:
        grants = {"shell.exec": {}}
        with pytest.raises(GrantViolation, match="no command_allowlist"):
            check_capability(grants, "shell.exec", {"cmd": "ls"})

    def test_http_fetch_valid(self) -> None:
        grants = {"http.fetch": {"host_allowlist": ["api.example.com"]}}
        check_capability(grants, "http.fetch", {"url": "https://api.example.com/data"})

    def test_http_fetch_host_not_allowed(self) -> None:
        grants = {"http.fetch": {"host_allowlist": ["api.example.com"]}}
        with pytest.raises(GrantViolation, match="not allowlisted"):
            check_capability(grants, "http.fetch", {"url": "https://evil.com"})

    def test_http_fetch_method_not_allowed(self) -> None:
        grants = {
            "http.fetch": {
                "host_allowlist": ["example.com"],
                "methods": ["GET"],
            }
        }
        with pytest.raises(GrantViolation, match="method"):
            check_capability(grants, "http.fetch", {"url": "https://example.com", "method": "POST"})
