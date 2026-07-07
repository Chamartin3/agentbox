"""Tests for WorkspaceConfig value type."""

from __future__ import annotations

import pytest

from agentbox.core.data.workenv import (
    AgentRef,
    McpRef,
    Permissions,
    ResourceRef,
    WorkspaceConfig,
)


class TestWorkspaceConfig:
    def test_round_trip_minimal(self) -> None:
        c = WorkspaceConfig(name="test-workspace", description="A test")
        yaml_text = c.to_yaml()
        c2 = WorkspaceConfig.from_yaml(yaml_text)
        assert c == c2
        assert c2.name == "test-workspace"
        assert c2.description == "A test"

    def test_round_trip_full(self) -> None:
        c = WorkspaceConfig(
            name="full-ws",
            description="Full config",
            env_doc="# Hello\nWorld",
            agents=[
                AgentRef(id="main-agent", role="main"),
                AgentRef(id="sub-1", role="subagent"),
            ],
            resources=[ResourceRef(id="res-1"), ResourceRef(id="res-2")],
            skills=[ResourceRef(id="skill-1")],
            mcp_servers=[
                McpRef(
                    name="server-1",
                    config={"url": "http://localhost:8080"},
                    disabled_tools=["tool-a"],
                ),
            ],
            permissions=Permissions(data={"allowed_tools": ["read"]}),
            env={"FOO": "bar"},
        )
        yaml_text = c.to_yaml()
        c2 = WorkspaceConfig.from_yaml(yaml_text)
        assert c == c2
        assert c2.agents[0].role == "main"
        assert c2.mcp_servers[0].disabled_tools == ["tool-a"]
        assert c2.env == {"FOO": "bar"}

    def test_round_trip_env_doc_resource_ref(self) -> None:
        c = WorkspaceConfig(
            name="ref-ws",
            env_doc=ResourceRef(id="res-env-doc"),
        )
        yaml_text = c.to_yaml()
        c2 = WorkspaceConfig.from_yaml(yaml_text)
        assert c == c2
        assert isinstance(c2.env_doc, ResourceRef)
        assert c2.env_doc.id == "res-env-doc"

    def test_round_trip_empty_permissions(self) -> None:
        c = WorkspaceConfig(name="empty-perms")
        yaml_text = c.to_yaml()
        c2 = WorkspaceConfig.from_yaml(yaml_text)
        assert c == c2
        assert c2.permissions.data == {}

    def test_validate_duplicate_agent(self) -> None:
        c = WorkspaceConfig(
            name="dup",
            agents=[AgentRef(id="a"), AgentRef(id="a")],
        )
        with pytest.raises(ValueError, match="Duplicate agent id"):
            c.validate()

    def test_validate_missing_agent_id(self) -> None:
        c = WorkspaceConfig(
            name="missing-id",
            agents=[AgentRef(id="")],
        )
        with pytest.raises(ValueError, match="agent ref missing id"):
            c.validate()

    def test_validate_missing_resource_id(self) -> None:
        c = WorkspaceConfig(
            name="missing-res",
            resources=[ResourceRef(id="")],
        )
        with pytest.raises(ValueError, match="resource ref missing id"):
            c.validate()

    def test_validate_ok(self) -> None:
        c = WorkspaceConfig(
            name="valid",
            agents=[AgentRef(id="a"), AgentRef(id="b")],
            resources=[ResourceRef(id="r1")],
            skills=[ResourceRef(id="s1")],
        )
        c.validate()  # should not raise
