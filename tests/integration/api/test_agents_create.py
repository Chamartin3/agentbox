"""Tests for agent creation and version file endpoints."""

from __future__ import annotations

from typing import Any

from agentbox.core.service.agents.service import AgentService


def test_create_agent_happy_path(client: Any) -> None:
    """POST /api/agents creates a new agent and returns 201."""
    req = {
        "id": "test_agent",
        "description": "A test agent",
        "runner": {"kind": "token", "model": "claude-3-sonnet"},
        "prompt": "You are a helpful assistant.",
        "author": "test_user",
        "changelog": "Initial creation",
    }
    resp = client.post("/api/agents", json=req)
    assert resp.status_code == 201
    data = resp.json()
    assert data["agent_id"] == "test_agent"
    assert data["version"] == 1
    assert isinstance(data["version_id"], int)


def test_create_agent_duplicate_id_returns_409(client: Any) -> None:
    """POST /api/agents with duplicate ID returns 409."""
    req = {
        "id": "test_agent",
        "description": "A test agent",
        "runner": {"kind": "token"},
        "author": "test_user",
        "changelog": "Initial creation",
    }
    # First creation succeeds
    resp1 = client.post("/api/agents", json=req)
    assert resp1.status_code == 201

    # Second creation with same ID fails
    resp2 = client.post("/api/agents", json=req)
    assert resp2.status_code == 409
    detail = resp2.json()["detail"]
    detail_str = detail if isinstance(detail, str) else detail.get("detail", "")
    assert "already exists" in detail_str


def test_create_agent_missing_changelog_returns_422(client: Any) -> None:
    """POST /api/agents without changelog returns 422."""
    req = {
        "id": "test_agent",
        "description": "A test agent",
        "runner": {"kind": "token"},
        "author": "test_user",
        # changelog missing (required)
    }
    resp = client.post("/api/agents", json=req)
    assert resp.status_code == 422


def test_upload_file_to_draft_succeeds(client: Any) -> None:
    """POST /api/agents/{id}/versions/{v}/files uploads file to draft."""
    # Create agent
    create_req = {
        "id": "test_agent",
        "description": "A test agent",
        "runner": {"kind": "token"},
        "author": "test_user",
        "changelog": "Initial",
    }
    create_resp = client.post("/api/agents", json=create_req)
    assert create_resp.status_code == 201

    # Upload file
    file_req = {
        "kind": "system",
        "name": "system.md",
        "content": "# System Prompt\nYou are helpful.",
    }
    upload_resp = client.post("/api/agents/test_agent/versions/1/files", json=file_req)
    assert upload_resp.status_code == 201
    data = upload_resp.json()
    assert isinstance(data["file_id"], int)
    assert len(data["sha256"]) == 64  # sha256 hex is 64 chars
    assert data["size"] == len(file_req["content"])


def test_upload_file_to_published_returns_409(client: Any) -> None:
    """Uploading to published version returns 409."""
    # Create agent
    create_req = {
        "id": "test_agent",
        "description": "A test agent",
        "runner": {"kind": "token"},
        "author": "test_user",
        "changelog": "Initial",
    }
    create_resp = client.post("/api/agents", json=create_req)
    assert create_resp.status_code == 201
    create_resp.json()["version_id"]

    # Publish the version
    svc = _get_svc()
    svc.publish_version("test_agent", 1, "Published for testing")

    # Try to upload file to published version
    file_req = {
        "kind": "system",
        "name": "system.md",
        "content": "# System Prompt",
    }
    upload_resp = client.post("/api/agents/test_agent/versions/1/files", json=file_req)
    assert upload_resp.status_code == 409


def test_upload_duplicate_sha_returns_409(client: Any) -> None:
    """Uploading file with duplicate sha256 returns 409."""
    # Create agent
    create_req = {
        "id": "test_agent",
        "description": "A test agent",
        "runner": {"kind": "token"},
        "author": "test_user",
        "changelog": "Initial",
    }
    create_resp = client.post("/api/agents", json=create_req)
    assert create_resp.status_code == 201

    # Upload first file
    file_req = {
        "kind": "system",
        "name": "system.md",
        "content": "Same content",
    }
    upload_resp1 = client.post("/api/agents/test_agent/versions/1/files", json=file_req)
    assert upload_resp1.status_code == 201

    # Try to upload same content again (different name, same sha256)
    file_req2 = {
        "kind": "reference",
        "name": "reference.md",
        "content": "Same content",  # Same content = same sha256
    }
    upload_resp2 = client.post(
        "/api/agents/test_agent/versions/1/files", json=file_req2
    )
    assert upload_resp2.status_code == 409


def test_delete_file_from_draft_succeeds_returns_204(client: Any) -> None:
    """DELETE /api/agents/{id}/versions/{v}/files/{fid} returns 204."""
    # Create agent
    create_req = {
        "id": "test_agent",
        "description": "A test agent",
        "runner": {"kind": "token"},
        "author": "test_user",
        "changelog": "Initial",
    }
    create_resp = client.post("/api/agents", json=create_req)
    assert create_resp.status_code == 201

    # Upload file
    file_req = {
        "kind": "system",
        "name": "system.md",
        "content": "# System Prompt",
    }
    upload_resp = client.post("/api/agents/test_agent/versions/1/files", json=file_req)
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["file_id"]

    # Delete file
    delete_resp = client.delete(f"/api/agents/test_agent/versions/1/files/{file_id}")
    assert delete_resp.status_code == 204

    # Verify file is gone
    svc = _get_svc()
    ver = svc.get_version("test_agent", 1)
    assert ver is not None
    files = svc.list_version_files(ver["id"])
    assert not any(f["id"] == file_id for f in files)


def test_delete_file_from_published_returns_409(client: Any) -> None:
    """DELETE file from published version returns 409."""
    # Create agent
    create_req = {
        "id": "test_agent",
        "description": "A test agent",
        "runner": {"kind": "token"},
        "author": "test_user",
        "changelog": "Initial",
    }
    create_resp = client.post("/api/agents", json=create_req)
    assert create_resp.status_code == 201

    # Upload file
    file_req = {
        "kind": "system",
        "name": "system.md",
        "content": "# System Prompt",
    }
    upload_resp = client.post("/api/agents/test_agent/versions/1/files", json=file_req)
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["file_id"]

    # Publish version
    svc = _get_svc()
    svc.publish_version("test_agent", 1, "Published")

    # Try to delete from published version
    delete_resp = client.delete(f"/api/agents/test_agent/versions/1/files/{file_id}")
    assert delete_resp.status_code == 409


def _get_svc() -> AgentService:
    """Helper to get the agent service (self-wires from settings)."""
    return AgentService()
