"""Resource materialization: render, tree, blob reads, and exports.

.. deprecated::
    These standalone functions are retained for backward compatibility
    with existing test code. New code should use ``ResourceService``
    directly from ``agentbox.core.service.resources.service``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from agentbox.core.agents.composition.rendering import render_for_type
from agentbox.core.resources.pydantic_export import schema_to_pydantic

from agentbox.core.service.resources.repo import (
    InvalidResource,
    ResourceNotFound,
)
from agentbox.core.service.resources.service import ResourceService

if TYPE_CHECKING:
    from agentbox.core.db import SessionStore

__all__ = [
    "get_blob",
    "render_resource",
    "get_tree",
    "export_pydantic",
    "validate_script_sample",
    "export_zip",
]


def _svc() -> ResourceService:
    return ResourceService()


def get_blob(resource_id: str, *, store: SessionStore, path: str = "", version_id: str | None = None) -> dict:  # noqa: ARG001
    return _svc().get_blob(resource_id, path=path, version_id=version_id)


def render_resource(resource_id: str, *, store: SessionStore, version_id: str | None = None) -> dict:  # noqa: ARG001
    return _svc().render_resource(resource_id, version_id=version_id)


def get_tree(resource_id: str, *, store: SessionStore, version_id: str | None = None) -> dict:  # noqa: ARG001
    return _svc().get_tree(resource_id, version_id=version_id)


def export_pydantic(resource_id: str, *, store: SessionStore, class_name: str = "Model", version_id: str | None = None) -> str:  # noqa: ARG001
    return _svc().export_pydantic(resource_id, class_name=class_name, version_id=version_id)


def validate_script_sample(resource_id: str, *, store: SessionStore, sample: Any, direction: Literal["input", "output"] = "input") -> dict:  # noqa: ARG001
    return _svc().validate_script_sample(resource_id, sample=sample, direction=direction)


def export_zip(resource_id: str, *, store: SessionStore, version_id: str | None = None) -> tuple[bytes, str]:  # noqa: ARG001
    return _svc().export_zip(resource_id, version_id=version_id)
