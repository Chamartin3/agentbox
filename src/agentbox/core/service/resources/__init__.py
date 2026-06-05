"""Service layer for the central resource repository.

Wraps the repo-resource CRUD, importer dispatch, version publishing,
blob/render/tree reads, and export helpers.
"""

from __future__ import annotations

from agentbox.core.service.resources.import_ import (
    import_host_path_version,
    import_schema_version,
    import_script_version,
    import_upload_version,
    import_zip_version,
)
from agentbox.core.service.resources.materialize import (
    export_pydantic,
    export_zip,
    get_blob,
    get_tree,
    render_resource,
    validate_script_sample,
)
from agentbox.core.service.resources.repo import (
    InvalidResource,
    NoActiveVersion,
    ResourceNotFound,
    create_resource,
    get_resource,
    list_resources,
    list_versions,
    publish_version,
    resolve_resource_id,
    rollback_resource,
    soft_delete_resource,
    update_resource,
)

__all__ = [
    "ResourceNotFound",
    "InvalidResource",
    "NoActiveVersion",
    "resolve_resource_id",
    "list_resources",
    "create_resource",
    "get_resource",
    "update_resource",
    "list_versions",
    "import_upload_version",
    "import_host_path_version",
    "import_zip_version",
    "import_schema_version",
    "import_script_version",
    "publish_version",
    "rollback_resource",
    "get_blob",
    "render_resource",
    "get_tree",
    "export_pydantic",
    "validate_script_sample",
    "export_zip",
    "soft_delete_resource",
]
