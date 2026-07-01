"""Resource importer dispatch service operations.

.. deprecated::
    These standalone functions are retained for backward compatibility
    with existing test code. New code should use ``ResourceService``
    directly from ``agentbox.core.service.resources.service``.
"""

from __future__ import annotations

from agentbox.core.service.resources.service import (
    ResourceService,
)

__all__ = [
    "import_upload_version",
    "import_host_path_version",
    "import_zip_version",
    "import_schema_version",
    "import_script_version",
]


def _svc() -> ResourceService:
    return ResourceService()


def import_upload_version(resource_id: str, *, filename: str, content: bytes, mime_type: str | None, changelog: str, draft: bool = False, actor: str | None = None) -> dict:
    return _svc().import_upload_version(
        resource_id, filename=filename, content=content, mime_type=mime_type,
        changelog=changelog, draft=draft, actor=actor,
    )


def import_host_path_version(resource_id: str, *, path: str, include: list[str], exclude: list[str], changelog: str, draft: bool = False, actor: str | None = None) -> dict:
    return _svc().import_host_path_version(
        resource_id, path=path, include=include, exclude=exclude,
        changelog=changelog, draft=draft, actor=actor,
    )


def import_zip_version(resource_id: str, *, filename: str, content: bytes, changelog: str, draft: bool = False, actor: str | None = None) -> dict:
    return _svc().import_zip_version(
        resource_id, filename=filename, content=content,
        changelog=changelog, draft=draft, actor=actor,
    )


def import_schema_version(resource_id: str, *, filename: str, content: bytes, changelog: str, draft: bool = False, actor: str | None = None) -> dict:
    return _svc().import_schema_version(
        resource_id, filename=filename, content=content,
        changelog=changelog, draft=draft, actor=actor,
    )


def import_script_version(resource_id: str, *, filename: str, content: bytes, changelog: str, language: str | None = None, input_schema_resource_id: str | None = None, output_schema_resource_id: str | None = None, draft: bool = False, actor: str | None = None) -> dict:
    return _svc().import_script_version(
        resource_id, filename=filename, content=content, changelog=changelog,
        language=language, input_schema_resource_id=input_schema_resource_id,
        output_schema_resource_id=output_schema_resource_id,
        draft=draft, actor=actor,
    )
