"""Unit tests for prefix-grouping rules."""

from __future__ import annotations

from agentbox.core.mcp.grouping import derive_groups, resolve_group_ref
from agentbox.core.mcp.tool_manifest import Tool


def _tool(name: str) -> Tool:
    return Tool(name=name)


# ---------------------------------------------------------------------------
# derive_groups
# ---------------------------------------------------------------------------


def test_get_prefix_becomes_read() -> None:
    tools = [_tool("jobpost_get_all")]
    groups = derive_groups("my-mcp", tools)
    assert "my-mcp.jobpost.read" in groups
    assert groups["my-mcp.jobpost.read"] == ["jobpost_get_all"]


def test_list_prefix_becomes_read() -> None:
    tools = [_tool("cv_list_openings")]
    groups = derive_groups("mcp", tools)
    assert "mcp.cv.read" in groups
    assert groups["mcp.cv.read"] == ["cv_list_openings"]


def test_search_prefix_becomes_read() -> None:
    tools = [_tool("db_search_candidates")]
    groups = derive_groups("mcp", tools)
    assert "mcp.db.read" in groups
    assert groups["mcp.db.read"] == ["db_search_candidates"]


def test_check_prefix_becomes_read() -> None:
    tools = [_tool("health_check_status")]
    groups = derive_groups("mcp", tools)
    assert "mcp.health.read" in groups
    assert groups["mcp.health.read"] == ["health_check_status"]


def test_write_action_goes_to_write() -> None:
    tools = [_tool("jobpost_create")]
    groups = derive_groups("my-mcp", tools)
    assert "my-mcp.jobpost.write" in groups
    assert groups["my-mcp.jobpost.write"] == ["jobpost_create"]


def test_write_action_with_underscore_prefix() -> None:
    tools = [_tool("jobpost_update_status")]
    groups = derive_groups("my-mcp", tools)
    assert "my-mcp.jobpost.write" in groups
    assert groups["my-mcp.jobpost.write"] == ["jobpost_update_status"]


def test_mixed_read_write_split() -> None:
    tools = [
        _tool("jobpost_get_all"),
        _tool("jobpost_create"),
        _tool("jobpost_delete"),
    ]
    groups = derive_groups("my-mcp", tools)
    assert groups["my-mcp.jobpost.read"] == ["jobpost_get_all"]
    assert set(groups["my-mcp.jobpost.write"]) == {"jobpost_create", "jobpost_delete"}


def test_all_prefix_contains_everything() -> None:
    tools = [
        _tool("jobpost_get_all"),
        _tool("jobpost_create"),
    ]
    groups = derive_groups("my-mcp", tools)
    assert set(groups["my-mcp.jobpost"]) == {"jobpost_get_all", "jobpost_create"}


def test_multiple_prefixes() -> None:
    tools = [
        _tool("cv_get"),
        _tool("cv_upload"),
        _tool("jobpost_list"),
        _tool("jobpost_create"),
    ]
    groups = derive_groups("mcp", tools)
    assert "mcp.cv.read" in groups
    assert "mcp.cv.write" in groups
    assert "mcp.jobpost.read" in groups
    assert "mcp.jobpost.write" in groups


def test_no_read_prefix_maps_to_write_only() -> None:
    tools = [_tool("system_reboot")]
    groups = derive_groups("mcp", tools)
    assert "mcp.system.read" not in groups
    assert "mcp.system.write" in groups
    assert "mcp.system" in groups


def test_select_prefix_becomes_read() -> None:
    tools = [_tool("candidate_select_best")]
    groups = derive_groups("mcp", tools)
    assert "mcp.candidate.read" in groups
    assert groups["mcp.candidate.read"] == ["candidate_select_best"]


def test_find_prefix_becomes_read() -> None:
    tools = [_tool("user_find_by_email")]
    groups = derive_groups("mcp", tools)
    assert "mcp.user.read" in groups
    assert groups["mcp.user.read"] == ["user_find_by_email"]


# ---------------------------------------------------------------------------
# resolve_group_ref
# ---------------------------------------------------------------------------


def test_resolve_explicit_server_group() -> None:
    groups = {"my-mcp.jobpost.read": ["jobpost_get_all", "jobpost_list"]}
    result = resolve_group_ref("@my-mcp:jobpost.read", groups)
    assert result == ["jobpost_get_all", "jobpost_list"]


def test_resolve_implicit_group() -> None:
    groups = {"mcp.cv.read": ["cv_get", "cv_list"]}
    result = resolve_group_ref("@cv.read", groups)
    assert result == ["cv_get", "cv_list"]


def test_resolve_mcp_tool_ref() -> None:
    groups = {}
    result = resolve_group_ref("mcp:my-mcp/cv_get", groups)
    assert result == ["cv_get"]


def test_unknown_group_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="unknown group"):
        resolve_group_ref("@nonexistent", {})


def test_non_group_ref_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="not a group reference"):
        resolve_group_ref("just_a_tool", {})
