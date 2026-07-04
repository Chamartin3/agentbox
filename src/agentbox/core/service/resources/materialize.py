"""Resource materialization: render, tree, blob reads, and exports.

.. deprecated::
    These standalone functions are retained for backward compatibility
    with existing test code. New code should use ``ResourceService``
    directly from ``agentbox.core.service.resources.service``.
"""

from __future__ import annotations

from typing import Any, Literal

from agentbox.core.data.rows import ResourceBlobRow
from agentbox.core.service.resources.service import ResourceService

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


def get_blob(resource_id: str, *, path: str = "", version_id: str | None = None) -> ResourceBlobRow:
    return _svc().get_blob(resource_id, path=path, version_id=version_id)


def render_resource(resource_id: str, *, version_id: str | None = None) -> dict:
    return _svc().render_resource(resource_id, version_id=version_id)


def get_tree(resource_id: str, *, version_id: str | None = None) -> dict:
    return _svc().get_tree(resource_id, version_id=version_id)


def export_pydantic(resource_id: str, *, class_name: str = "Model", version_id: str | None = None) -> str:
    return _svc().export_pydantic(resource_id, class_name=class_name, version_id=version_id)


def validate_script_sample(resource_id: str, *, sample: Any, direction: Literal["input", "output"] = "input") -> dict:
    return _svc().validate_script_sample(resource_id, sample=sample, direction=direction)


def export_zip(resource_id: str, *, version_id: str | None = None) -> tuple[bytes, str]:
    return _svc().export_zip(resource_id, version_id=version_id)
