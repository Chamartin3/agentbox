"""Tests for the slot + attach_as_reference extensions on prompt bindings."""

from __future__ import annotations

import json
from typing import Any


def _create_resource(client: Any, slug: str, type_: str, display: str) -> str:
    r = client.post(
        "/api/repo-resources",
        json={"slug": slug, "type": type_, "display_name": display},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _upload_schema(client: Any, rid: str) -> None:
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    r = client.post(
        f"/api/repo-resources/{rid}/versions/upload-schema",
        params={"changelog": "init"},
        files={"file": ("s.json", json.dumps(schema), "application/json")},
    )
    assert r.status_code == 201, r.text
    versions = client.get(f"/api/repo-resources/{rid}/versions").json()["items"]
    vid = versions[0]["id"]
    r = client.post(
        f"/api/repo-resources/{rid}/versions/{vid}/publish",
        json={"reason": "publish"},
    )
    assert r.status_code == 200, r.text


def _upload_document(client: Any, rid: str, body: str) -> None:
    r = client.post(
        f"/api/repo-resources/{rid}/versions/upload",
        params={"changelog": "init"},
        files={"file": ("doc.md", body, "text/markdown")},
    )
    assert r.status_code == 201, r.text
    versions = client.get(f"/api/repo-resources/{rid}/versions").json()["items"]
    vid = versions[0]["id"]
    r = client.post(
        f"/api/repo-resources/{rid}/versions/{vid}/publish",
        json={"reason": "publish"},
    )
    assert r.status_code == 200, r.text


def test_duplicate_slot_rejected(client: Any) -> None:
    schema_a = _create_resource(client, "schema-a", "schema", "A")
    schema_b = _create_resource(client, "schema-b", "schema", "B")
    _upload_schema(client, schema_a)
    _upload_schema(client, schema_b)

    r = client.put(
        "/api/agents/agent-x/prompt-resources",
        json={
            "reason": "two output schemas",
            "bindings": [
                {"resource_id": schema_a, "slot": "output_schema"},
                {"resource_id": schema_b, "slot": "output_schema"},
            ],
        },
    )
    assert r.status_code == 400, r.text
    assert "Duplicate" in r.json()["detail"]


def test_schema_slot_round_trip(client: Any) -> None:
    schema = _create_resource(client, "out-schema", "schema", "Out")
    _upload_schema(client, schema)

    r = client.put(
        "/api/agents/agent-y/prompt-resources",
        json={
            "reason": "attach output schema",
            "bindings": [{"resource_id": schema, "slot": "output_schema"}],
        },
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["slot"] == "output_schema"
    assert items[0]["marker"] is None
    assert items[0]["mode"] is None


def test_reference_toggle_in_preview(client: Any) -> None:
    doc = _create_resource(client, "guidelines", "document", "Guidelines")
    _upload_document(client, doc, "DO things carefully.")

    base = {
        "resource_id": doc,
        "marker": "doc",
        "mode": "inline",
    }
    # Without reference flag
    r = client.post(
        "/api/agents/agent-z/prompt-resources/preview",
        json={
            "template": "PROMPT BODY {{resource:doc}}",
            "bindings": [{**base, "attach_as_reference": False}],
        },
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert "References" not in out["rendered_prompt"]
    assert out["references"] == []
    assert out["raw_text_output"] is True

    # With reference flag
    r = client.post(
        "/api/agents/agent-z/prompt-resources/preview",
        json={
            "template": "PROMPT BODY {{resource:doc}}",
            "bindings": [{**base, "attach_as_reference": True}],
        },
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert "## References" in out["rendered_prompt"]
    assert "DO things carefully." in out["rendered_prompt"]
    assert len(out["references"]) == 1


def test_raw_text_output_when_no_output_schema(client: Any) -> None:
    schema = _create_resource(client, "in-schema-only", "schema", "InOnly")
    _upload_schema(client, schema)
    r = client.post(
        "/api/agents/agent-rt/prompt-resources/preview",
        json={
            "template": "hello",
            "bindings": [{"resource_id": schema, "slot": "input_schema"}],
        },
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["raw_text_output"] is True
    assert out["output_schema"] is None
    assert out["input_schema"]["resource_id"] == schema
