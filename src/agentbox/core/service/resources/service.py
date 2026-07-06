"""ResourceService — the resource-domain public service object.

All repo-resource CRUD, version lifecycle, import dispatch, blob reads,
materialization, shared resource CRUD, and prompt/workspace bindings live here.

Callers construct with no arguments:  ``ResourceService()``
The Database is resolved internally from settings.

Import constraints (resources-foundation):
  ``core.resources`` (the domain) must not import agents/workspaces/execution.
  This *service* module (``core.service.resources``) is not subject to that rule
  and may freely import from other service layers and domain helpers.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator

from agentbox.core.agents.composition.rendering import render_for_type
from agentbox.core.data.constants import ResourceType
from agentbox.core.data.payload_types import (
    EnrichedPromptBindingRow,
    EnrichedWorkspaceBindingRow,
    MaterializeConflict,
    MaterializeDryRunEntry,
    MaterializeDryRunResult,
    PromptBindingItemsResult,
    PromptBindingSpec,
    PromptPreviewResult,
    PromptResourcesResult,
    RenderedResourceResult,
    ResourceDetailResult,
    ResourceListResult,
    ResourcePreviewMode,
    ResourcePreviewModesResult,
    ResourceTreeResult,
    ResourceVersionsResult,
    SchemaValidationErrorView,
    ScriptSampleValidationResult,
    SkillBindingsResult,
    SkillCatalogItem,
    WorkspaceBindingItemsResult,
    WorkspaceBindingSpec,
    WorkspaceResourcesResult,
)
from agentbox.core.data.records import SharedResourceRecord
from agentbox.core.data.rows import (
    AgentPromptBindingRow,
    RepoResourceRow,
    ResourceBlobRow,
    ResourceVersionRow,
    WorkspaceFileBindingRow,
)
from agentbox.core.resources.importers.base import ImporterContext
from agentbox.core.resources.importers.host_path import HostPathImporter
from agentbox.core.resources.importers.schema import SchemaImporter
from agentbox.core.resources.importers.script import ScriptImporter
from agentbox.core.resources.importers.skill import SkillImporter
from agentbox.core.resources.importers.upload import UploadImporter
from agentbox.core.resources.importers.zip import ZipUploadImporter
from agentbox.core.resources.pydantic_export import schema_to_pydantic
from agentbox.core.service.agents.service import AgentService
from agentbox.core.service.base import Service


class ResourceNotFound(LookupError):
    def __init__(self, resource_id: str) -> None:
        super().__init__(f"resource {resource_id!r} not found")
        self.resource_id = resource_id


class InvalidResource(ValueError):
    """Resource exists but the requested operation is invalid for it."""


class NoActiveVersion(LookupError):
    def __init__(self, resource_id: str) -> None:
        super().__init__(f"no active version for resource {resource_id!r}")
        self.resource_id = resource_id


class BindingError(ValueError):
    """Binding validation rejection."""


class AgentVersionMissing(LookupError):
    def __init__(self, agent_id: str) -> None:
        super().__init__(f"no agent version found for {agent_id!r}")
        self.agent_id = agent_id


class ResourceService(Service):
    """Resource domain: shared resources, repo resources, version lifecycle,
    blob storage, import dispatch, materialization, and bindings.
    """

    def __init__(self) -> None:
        super().__init__()
        self._resources = self._db.resources
        self._resource_versions = self._db.resource_versions
        self._resource_blobs = self._db.resource_blobs
        self._active_resource_versions = self._db.active_resource_versions
        self._shared_resources = self._db.shared_resources
        self._prompt_bindings = self._db.agent_prompt_resource_bindings
        self._file_bindings = self._db.workspace_file_resource_bindings

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _resolve_or_raise(self, id_or_slug: str) -> str:
        rid = self.resolve_resource_id(id_or_slug)
        if rid is None:
            raise ResourceNotFound(id_or_slug)
        return rid

    def _active_version_or_raise(self, resource_id: str) -> ResourceVersionRow:
        active = self._resource_versions.get_active_version(resource_id)
        if not active:
            raise NoActiveVersion(resource_id)
        return active

    def _require_resource(self, resource_id: str) -> RepoResourceRow:
        r = self._resources.get_resource(resource_id)
        if not r:
            raise ResourceNotFound(resource_id)
        return r

    def _import_with(
        self,
        resource_id: str,
        importer: Any,
        *,
        changelog: str,
        draft: bool,
        actor: str | None,
    ) -> ResourceVersionRow:
        try:
            result = importer.run(ImporterContext(actor=actor, changelog=changelog))
        except (FileNotFoundError, ValueError) as exc:
            raise InvalidResource(str(exc)) from exc
        try:
            return self._resource_versions.import_version(
                resource_id,
                result.blobs,
                import_source=result.import_source,
                changelog=changelog,
                source_metadata=result.source_metadata,
                metadata=result.metadata,
                draft=draft,
                created_by=actor,
            )
        except ValueError as exc:
            raise InvalidResource(str(exc)) from exc

    # -----------------------------------------------------------------------
    # Repo resource ID resolution
    # -----------------------------------------------------------------------

    def resolve_resource_id(self, id_or_slug: str) -> str | None:
        """Return the resource id for a given id or slug, or None if not found."""
        if not id_or_slug:
            return None
        r = self._resources.get_resource(id_or_slug)
        if r:
            return r["id"]
        r = self._resources.get_by_slug(id_or_slug)
        if r:
            return r["id"]
        if "." in id_or_slug and "/" not in id_or_slug:
            candidate = id_or_slug.replace(".", "/")
            r = self._resources.get_by_slug(candidate)
            if r:
                return r["id"]
        return None

    # -----------------------------------------------------------------------
    # Repo resource CRUD
    # -----------------------------------------------------------------------

    def list_resources(
        self,
        *,
        type: ResourceType | None = None,
        query: str | None = None,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> ResourceListResult:
        """Paginated list of repo resources."""
        type_str = type.value if isinstance(type, ResourceType) else type
        items = self._resources.list_resources(
            type=type_str,
            query=query,
            include_deleted=include_deleted,
            limit=limit,
            offset=offset,
        )
        total = self._resources.count_resources(
            type=type_str, query=query, include_deleted=include_deleted
        )
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    def create_resource(
        self,
        *,
        slug: str,
        type: ResourceType | str,
        display_name: str,
        description: str | None = None,
        tags: list[str] | None = None,
        created_by: str | None = None,
    ) -> RepoResourceRow:
        """Create a new repo resource."""
        type_str = type.value if isinstance(type, ResourceType) else type
        try:
            return self._resources.create_resource(
                slug=slug,
                type=type_str,
                display_name=display_name,
                description=description,
                tags=tags or [],
                created_by=created_by,
            )
        except ValueError as exc:
            raise InvalidResource(str(exc)) from exc

    def get_resource(self, resource_id: str) -> ResourceDetailResult:
        """Return {resource, active_version} for a repo resource."""
        rid = self._resolve_or_raise(resource_id)
        r = self._resources.get_resource(rid)
        active = (
            self._resource_versions.get_active_version(rid)
            if r and r.get("active_version_id")
            else None
        )
        return {"resource": r, "active_version": active}

    def get_resource_row(self, resource_id: str) -> RepoResourceRow | None:
        """Return the raw resource row dict by id, or None."""
        return self._resources.get_resource(resource_id)

    def get_by_slug(self, slug: str) -> RepoResourceRow | None:
        """Return the raw resource row dict by slug, or None."""
        return self._resources.get_by_slug(slug)

    def update_resource(
        self,
        resource_id: str,
        *,
        display_name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> RepoResourceRow:
        """Update resource metadata and return updated row."""
        rid = self._resolve_or_raise(resource_id)
        updated = self._resources.update_resource(
            rid, display_name=display_name, description=description, tags=tags
        )
        if updated is None:
            raise ResourceNotFound(resource_id)
        return updated

    def list_versions(self, resource_id: str) -> ResourceVersionsResult:
        """Return {items: [...]} of all versions for a repo resource."""
        rid = self._resolve_or_raise(resource_id)
        return {"items": self._resource_versions.list_versions(rid)}

    def publish_version(
        self,
        resource_id: str,
        version_id: str,
        *,
        reason: str,
        actor: str | None = None,
    ) -> ResourceVersionRow:
        """Promote a draft version to active."""
        v = self._resource_versions.get_version(version_id)
        if not v or v["resource_id"] != resource_id:
            raise ResourceNotFound(version_id)
        try:
            return self._resource_versions.publish_version(
                version_id, reason=reason, activated_by=actor
            )
        except ValueError as exc:
            raise InvalidResource(str(exc)) from exc

    def rollback_resource(
        self,
        resource_id: str,
        *,
        target_version: int,
        reason: str,
        actor: str | None = None,
    ) -> ResourceVersionRow:
        """Create a new version copying blobs from ``target_version``."""
        self._require_resource(resource_id)
        try:
            return self._resource_versions.rollback_resource(
                resource_id, target_version, reason=reason, activated_by=actor
            )
        except ValueError as exc:
            raise InvalidResource(str(exc)) from exc

    def soft_delete_resource(self, resource_id: str, *, reason: str) -> None:
        """Soft-delete a repo resource."""
        self._require_resource(resource_id)
        self._resources.soft_delete(resource_id, reason=reason)

    # -----------------------------------------------------------------------
    # Version import operations
    # -----------------------------------------------------------------------

    def import_upload_version(
        self,
        resource_id: str,
        *,
        filename: str,
        content: bytes,
        mime_type: str | None,
        changelog: str,
        draft: bool = False,
        actor: str | None = None,
    ) -> ResourceVersionRow:
        """Import a single-file upload as a new version."""
        self._require_resource(resource_id)
        importer = UploadImporter(
            filename=filename or "upload.bin", content=content, mime_type=mime_type
        )
        return self._import_with(
            resource_id, importer, changelog=changelog, draft=draft, actor=actor
        )

    def import_host_path_version(
        self,
        resource_id: str,
        *,
        path: str,
        include: list[str],
        exclude: list[str],
        changelog: str,
        draft: bool = False,
        actor: str | None = None,
    ) -> ResourceVersionRow:
        """Import from a host filesystem path as a new version."""
        resource = self._require_resource(resource_id)
        importer_cls = (
            SkillImporter if resource["type"] == "skill" else HostPathImporter
        )
        default_exclude = importer_cls.__dataclass_fields__["exclude"].default_factory()
        importer = importer_cls(
            root=Path(path),
            include=tuple(include),
            exclude=tuple(exclude) or default_exclude,
        )
        return self._import_with(
            resource_id, importer, changelog=changelog, draft=draft, actor=actor
        )

    def import_zip_version(
        self,
        resource_id: str,
        *,
        filename: str,
        content: bytes,
        changelog: str,
        draft: bool = False,
        actor: str | None = None,
    ) -> ResourceVersionRow:
        """Import a ZIP archive as a new version (folder/skill only)."""
        resource = self._require_resource(resource_id)
        if resource["type"] not in ("folder", "skill"):
            raise InvalidResource(
                f"zip upload only valid for folder/skill (got {resource['type']!r})"
            )
        importer = ZipUploadImporter(
            filename=filename or "upload.zip",
            content=content,
            as_skill=resource["type"] == "skill",
        )
        return self._import_with(
            resource_id, importer, changelog=changelog, draft=draft, actor=actor
        )

    def import_schema_version(
        self,
        resource_id: str,
        *,
        filename: str,
        content: bytes,
        changelog: str,
        draft: bool = False,
        actor: str | None = None,
    ) -> ResourceVersionRow:
        """Import a JSON schema file as a new version (schema resources only)."""
        resource = self._require_resource(resource_id)
        if resource["type"] != "schema":
            raise InvalidResource("resource is not of type 'schema'")
        importer = SchemaImporter(filename=filename or "schema.json", content=content)
        return self._import_with(
            resource_id, importer, changelog=changelog, draft=draft, actor=actor
        )

    def import_script_version(
        self,
        resource_id: str,
        *,
        filename: str,
        content: bytes,
        changelog: str,
        language: str | None = None,
        input_schema_resource_id: str | None = None,
        output_schema_resource_id: str | None = None,
        draft: bool = False,
        actor: str | None = None,
    ) -> ResourceVersionRow:
        """Import a script file as a new version (script resources only)."""
        resource = self._require_resource(resource_id)
        if resource["type"] != "script":
            raise InvalidResource("resource is not of type 'script'")
        importer = ScriptImporter(
            filename=filename or "script",
            content=content,
            language=language,
            input_schema_resource_id=input_schema_resource_id,
            output_schema_resource_id=output_schema_resource_id,
        )
        return self._import_with(
            resource_id, importer, changelog=changelog, draft=draft, actor=actor
        )

    # -----------------------------------------------------------------------
    # Materialization & rendering
    # -----------------------------------------------------------------------

    def get_blob(
        self,
        resource_id: str,
        *,
        path: str = "",
        version_id: str | None = None,
    ) -> ResourceBlobRow:
        """Return a blob dict for the given resource and path."""
        rid = self._resolve_or_raise(resource_id)
        vid: str = version_id or self._active_version_or_raise(rid)["id"]
        blob = self._resource_blobs.get_blob(vid, path)
        if not blob:
            raise ResourceNotFound(f"blob @ {path!r}")
        return blob

    def render_resource(
        self, resource_id: str, *, version_id: str | None = None
    ) -> RenderedResourceResult:
        """Render a resource as text (inline / manifest / skill_primer)."""
        rid = self._resolve_or_raise(resource_id)
        resource = self._require_resource(rid)
        vid: str = version_id or self._active_version_or_raise(rid)["id"]
        blobs = list(self._resource_blobs.iter_blobs(vid))
        rendered = render_for_type(resource["type"], blobs)
        return {
            "resource_id": rid,
            "version_id": vid,
            "text": rendered["text"],
            "metadata": rendered["metadata"],
        }

    def get_tree(self, resource_id: str, *, version_id: str | None = None) -> ResourceTreeResult:
        """Return the file tree for a versioned resource."""
        rid = self._resolve_or_raise(resource_id)
        vid: str = version_id or self._active_version_or_raise(rid)["id"]
        return {
            "version_id": vid,
            "entries": [
                {
                    "relative_path": b.get("relative_path") or "",
                    "size_bytes": b.get("size_bytes"),
                    "mime_type": b.get("mime_type"),
                }
                for b in self._resource_blobs.iter_blobs(vid)
            ],
        }

    def export_pydantic(
        self,
        resource_id: str,
        *,
        class_name: str = "Model",
        version_id: str | None = None,
    ) -> str:
        """Export a schema resource as Python Pydantic model source."""
        resource = self._require_resource(resource_id)
        if resource["type"] != "schema":
            raise InvalidResource("resource is not of type 'schema'")
        vid: str = version_id or self._active_version_or_raise(resource_id)["id"]
        blob = self._resource_blobs.get_blob(vid, "")
        if not blob:
            raise ResourceNotFound("schema blob")
        schema_text = blob.get("content_text") or blob["content"].decode("utf-8")
        try:
            return schema_to_pydantic(schema_text, class_name=class_name)
        except Exception as exc:
            raise InvalidResource(f"export failed: {exc}") from exc

    def validate_script_sample(
        self,
        resource_id: str,
        *,
        sample: Any,
        direction: Literal["input", "output"] = "input",
    ) -> ScriptSampleValidationResult:
        """Validate a sample against the script's bound schema."""
        resource = self._require_resource(resource_id)
        if resource["type"] != "script":
            raise InvalidResource("resource is not of type 'script'")
        active = self._active_version_or_raise(resource_id)
        raw_meta = active.get("metadata_json")
        metadata = json.loads(raw_meta) if raw_meta else {}
        key = "input_schema_resource_id" if direction == "input" else "output_schema_resource_id"
        schema_id = metadata.get(key)
        if not schema_id:
            raise InvalidResource(f"script has no bound {direction} schema")
        schema_active = self._resource_versions.get_active_version(schema_id)
        if not schema_active:
            raise InvalidResource("bound schema has no active version")
        schema_blob = self._resource_blobs.get_blob(schema_active["id"], "")
        if not schema_blob:
            raise InvalidResource("schema blob missing")
        schema_doc = json.loads(schema_blob.get("content_text") or schema_blob["content"])
        validator = Draft202012Validator(schema_doc)
        errors: list[SchemaValidationErrorView] = [
            {"path": list(e.absolute_path), "message": e.message}
            for e in validator.iter_errors(sample)
        ]
        return {"valid": not errors, "errors": errors, "schema_resource_id": schema_id}

    def export_zip(
        self, resource_id: str, *, version_id: str | None = None
    ) -> tuple[bytes, str]:
        """Export a folder/skill resource as a ZIP archive."""
        resource = self._require_resource(resource_id)
        if resource["type"] not in ("folder", "skill"):
            raise InvalidResource("zip export only supported for folder/skill")
        vid: str = version_id or self._active_version_or_raise(resource_id)["id"]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for blob in self._resource_blobs.iter_blobs(vid):
                rel = blob.get("relative_path") or ""
                if not rel:
                    continue
                zf.writestr(rel, blob["content"])
        filename = f"{resource['slug'].replace(':', '_')}.zip"
        return buf.getvalue(), filename

    def preview_modes(self, resource_id: str) -> ResourcePreviewModesResult:
        """Return available preview modes for a resource."""
        resource = self._resources.get_resource(resource_id)
        if not resource:
            raise ResourceNotFound(resource_id)
        active = self._resource_versions.get_active_version(resource_id)
        if not active:
            return {"modes": []}
        blobs = list(self._resource_blobs.iter_blobs(active["id"]))
        rtype = resource["type"]

        def _mode(mode: str) -> ResourcePreviewMode:
            rendered = render_for_type(rtype, blobs)
            return {"mode": mode, "text": rendered["text"], "metadata": rendered["metadata"]}

        modes: list[ResourcePreviewMode] = []
        if rtype == "document":
            modes.append(_mode("inline"))
        if rtype == "folder":
            modes.append(_mode("manifest"))
        if rtype == "skill":
            modes.append(_mode("skill_primer"))
            modes.append(
                {"mode": "name_only", "text": f"- {resource['display_name']}", "metadata": {"role": "name_only"}}
            )
        return {"modes": modes}

    # -----------------------------------------------------------------------
    # Prompt (agent) resource bindings
    # -----------------------------------------------------------------------

    def list_prompt_bindings(self, agent_id: str) -> list[AgentPromptBindingRow]:
        return self._prompt_bindings.list_for_agent(agent_id)

    def replace_prompt_bindings(
        self, agent_id: str, bindings: list[PromptBindingSpec], *, reason: str, actor: str | None = None
    ) -> list[AgentPromptBindingRow]:
        return self._prompt_bindings.replace_for_agent(agent_id, bindings, reason=reason, actor=actor)

    def list_workspace_file_bindings(self, workspace_id: str) -> list[WorkspaceFileBindingRow]:
        return self._file_bindings.list_for_workspace(workspace_id)

    def replace_workspace_file_bindings(
        self, workspace_id: str, bindings: list[WorkspaceBindingSpec], *, reason: str, actor: str | None = None
    ) -> list[WorkspaceFileBindingRow]:
        return self._file_bindings.replace_for_workspace(workspace_id, bindings, reason=reason, actor=actor)

    def list_prompt_resources(self, agent_id: str) -> PromptResourcesResult:
        """Return enriched prompt bindings for an agent."""
        bindings = self._prompt_bindings.list_for_agent(agent_id)
        enriched: list[EnrichedPromptBindingRow] = []
        for b in bindings:
            resource = self._resources.get_resource(b["resource_id"])
            active = (
                self._resource_versions.get_active_version(b["resource_id"])
                if resource
                else None
            )
            enriched.append(
                {
                    "id": b["id"],
                    "agent_id": b["agent_id"],
                    "resource_id": b["resource_id"],
                    "marker": b["marker"],
                    "mode": b["mode"],
                    "slot": b["slot"],
                    "attach_as_reference": bool(b.get("attach_as_reference")),
                    "pinned_version_id": b["pinned_version_id"],
                    "display_order": b["display_order"],
                    "required": b["required"],
                    "changelog": b["changelog"],
                    "created_at": b["created_at"],
                    "created_by": b["created_by"],
                    "resource_slug": resource["slug"] if resource else None,
                    "resource_type": resource["type"] if resource else None,
                    "resource_display_name": resource["display_name"] if resource else None,
                    "active_version_id": active["id"] if active else None,
                }
            )
        return {"items": enriched}

    def replace_prompt_resources(
        self,
        agent_id: str,
        bindings: list[PromptBindingSpec],
        *,
        reason: str,
        actor: str | None = None,
    ) -> PromptBindingItemsResult:
        """Atomically replace all prompt bindings for an agent."""
        try:
            return {"items": self._prompt_bindings.replace_for_agent(agent_id, bindings, reason=reason, actor=actor)}
        except ValueError as exc:
            raise BindingError(str(exc)) from exc

    def preview_prompt(
        self,
        agent_id: str,
        *,
        template: str | None = None,
        bindings_override: list[PromptBindingSpec] | None = None,
    ) -> PromptPreviewResult:
        """Render a preview of the agent prompt with resource bindings resolved.

        Delegates to ``AgentService.render_agent_prompt_preview`` which owns
        the composed-prompt rendering until ``render_agent_prompt_preview``
        is migrated fully to managers (Phase C).
        """
        agent_svc = AgentService()
        if template is None:
            agent_def = agent_svc.resolve_agent(agent_id)
            if agent_def is None:
                raise AgentVersionMissing(agent_id)
            template = agent_def.prompt or ""
        return agent_svc.render_agent_prompt_preview(
            agent_id=agent_id,
            template=template,
            bindings_override=bindings_override,
        )

    # -----------------------------------------------------------------------
    # Workspace file resource bindings
    # -----------------------------------------------------------------------

    def list_workspace_resources(self, workspace_id: str) -> WorkspaceResourcesResult:
        """Return enriched workspace file bindings."""
        bindings = self._file_bindings.list_for_workspace(workspace_id)
        enriched: list[EnrichedWorkspaceBindingRow] = []
        for b in bindings:
            resource = self._resources.get_resource(b["resource_id"])
            active = (
                self._resource_versions.get_active_version(b["resource_id"])
                if resource
                else None
            )
            enriched.append(
                {
                    **b,
                    "resource_slug": resource["slug"] if resource else None,
                    "resource_type": resource["type"] if resource else None,
                    "active_version_id": active["id"] if active else None,
                }
            )
        return {"items": enriched}

    def replace_workspace_resources(
        self,
        workspace_id: str,
        bindings: list[WorkspaceBindingSpec],
        *,
        reason: str,
        actor: str | None = None,
    ) -> WorkspaceBindingItemsResult:
        """Atomically replace workspace file bindings."""
        try:
            items = self._file_bindings.replace_for_workspace(
                workspace_id, bindings, reason=reason, actor=actor
            )
        except ValueError as exc:
            raise BindingError(str(exc)) from exc
        return {"items": items}

    def dry_run_workspace_resources(self, workspace_id: str) -> MaterializeDryRunResult:
        """Compute the materialization plan without writing anything."""
        bindings = self._file_bindings.list_for_workspace(workspace_id)
        entries: list[MaterializeDryRunEntry] = []
        seen_paths: dict[str, str] = {}
        conflicts: list[MaterializeConflict] = []
        for b in bindings:
            resource = self._resources.get_resource(b["resource_id"])
            if not resource:
                conflicts.append(
                    {"binding_id": b["id"], "issue": f"resource {b['resource_id']!r} not found"}
                )
                continue
            version_id = b.get("pinned_version_id")
            if not version_id:
                active = self._resource_versions.get_active_version(b["resource_id"])
                if not active:
                    conflicts.append(
                        {"binding_id": b["id"], "issue": f"resource {resource['slug']} has no active version"}
                    )
                    continue
                version_id = active["id"]
            blobs = list(self._resource_blobs.iter_blobs(version_id))
            target_path = b.get("target_path") or resource["display_name"]
            entries.append(
                {
                    "binding_id": b["id"],
                    "resource_id": b["resource_id"],
                    "resource_slug": resource["slug"],
                    "resource_type": resource["type"],
                    "version_id": version_id,
                    "target_path": target_path,
                    "file_count": len(blobs),
                    "materialize_mode": b["materialize_mode"],
                    "on_conflict": b["on_conflict"],
                }
            )
            if target_path in seen_paths:
                conflicts.append(
                    {"binding_id": b["id"], "issue": f"target_path {target_path!r} also used by binding {seen_paths[target_path]}"}
                )
            else:
                seen_paths[target_path] = b["id"]
        return {"entries": entries, "conflicts": conflicts}

    # -----------------------------------------------------------------------
    # Workspace skill bindings
    # -----------------------------------------------------------------------

    def list_workspace_skill_bindings(self, workspace_id: str) -> SkillBindingsResult:
        """Return all skill resources with a 'bound' flag for the workspace."""
        catalog = self._resources.list_resources(type="skill", limit=500)
        current = self._file_bindings.list_for_workspace(workspace_id)
        bound_ids: set[str] = set()
        for b in current:
            resource = self._resources.get_resource(b["resource_id"])
            if resource and resource.get("type") == "skill":
                bound_ids.add(b["resource_id"])
        items: list[SkillCatalogItem] = [{**r, "bound": r["id"] in bound_ids} for r in catalog]
        return {"items": items}

    def replace_workspace_skill_bindings(
        self,
        workspace_id: str,
        skill_resource_ids: list[str],
        *,
        reason: str = "skill bindings update",
        actor: str | None = None,
    ) -> WorkspaceBindingItemsResult:
        """Replace only the skill-type bindings for a workspace."""
        try:
            items = self._file_bindings.replace_skill_bindings(
                workspace_id, skill_resource_ids, reason=reason, actor=actor
            )
        except ValueError as exc:
            raise BindingError(str(exc)) from exc
        return {"items": items}

    # -----------------------------------------------------------------------
    # Shared resources (legacy cross-consumer API; will outlive the repo API)
    # -----------------------------------------------------------------------

    def get_shared_resource(self, id: str, version: int) -> SharedResourceRecord | None:
        return self._shared_resources.get_versioned(id, version)

    def get_active_shared_resource(self, id: str) -> SharedResourceRecord | None:
        return self._shared_resources.get_active(id)

    def list_shared_resources(
        self,
        *,
        kind: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SharedResourceRecord]:
        return self._shared_resources.list_active(kind=kind, q=q, limit=limit, offset=offset)

    def count_shared_resources(self, *, kind: str | None = None, q: str | None = None) -> int:
        return self._shared_resources.count_active(kind=kind, q=q)

    def list_shared_resource_versions(
        self, id: str, *, limit: int = 50, offset: int = 0
    ) -> list[SharedResourceRecord]:
        return self._shared_resources.list_versions(id, limit=limit, offset=offset)

    def create_shared_resource(
        self,
        id: str,
        kind: str,
        name: str,
        *,
        description: str | None = None,
        content: str | None = None,
        config_json: str | None = None,
        author: str | None = None,
        changelog: str | None = None,
        tags: list[str] | None = None,
        activate: bool = True,
    ) -> SharedResourceRecord:
        return self._shared_resources.create_resource(
            id, kind, name,
            description=description,
            content=content,
            config_json=config_json,
            author=author,
            changelog=changelog,
            tags=tags,
            activate=activate,
        )

    def create_shared_resource_version(
        self,
        id: str,
        *,
        content: str | None = None,
        config_json: str | None = None,
        author: str | None = None,
        changelog: str | None = None,
        activate: bool = False,
        **fields_to_update,
    ) -> SharedResourceRecord:
        return self._shared_resources.create_version(
            id,
            content=content,
            config_json=config_json,
            author=author,
            changelog=changelog,
            activate=activate,
            **fields_to_update,
        )

    def activate_shared_resource(self, id: str, version: int) -> SharedResourceRecord:
        return self._shared_resources.activate_version(id, version)

