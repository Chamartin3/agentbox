"""Workspace CLI renderer — typed output methods for workspace commands.

Formatting lives here, never in command bodies. Command modules call
these methods on ``ctx.obj.render.workspace`` with pre-fetched data.
"""

from __future__ import annotations

import json as _json
from collections.abc import Sequence
from pathlib import Path

from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from agentbox.core.data.payload_types import (
    GeneratedConfigsResult,
    GeneratedSkillsResult,
    MaterializeConflict,
    MaterializeDryRunEntry,
    PermissionsView,
    SkillListItem,
    WorkspaceMcpToolsResult,
)
from agentbox.cli.shared.render import Renderer
from agentbox.core.service import (
    WorkspaceFileBindingRow,
    WorkspaceMcpOverrideRow,
    WorkspaceMcpToolOverrideRow,
)
from agentbox.core.workspaces import WorkspaceInfo


class WorkspaceRenderer(Renderer):
    """Typed render methods for workspace contracts — formatting lives here, never in command bodies."""

    # ------------------------------------------------------------------
    # Workspace listing (ws ls)
    # ------------------------------------------------------------------

    def workspaces_table(self, rows: Sequence[WorkspaceInfo]) -> None:
        """Render a table of agents and their workspaces."""
        if not rows:
            self.warn("No agents declared.")
            return

        table = Table(
            title="Workspaces", title_style="bold", header_style="bold cyan",
            padding=(0, 1),
        )
        table.add_column("State", justify="center", width=7)
        table.add_column("Agent", style="bold")
        table.add_column("Path", style="dim")
        table.add_column("Context", justify="center")
        table.add_column("Skills", justify="right", style="magenta")

        for w in rows:
            if w.ephemeral:
                state = Text("EPH", style="bold yellow")
            elif w.exists:
                state = Text("OK", style="bold green")
            else:
                state = Text("NEW", style="bold blue")
            table.add_row(
                state, w.agent_id, str(w.path),
                self.check(w.has_context_doc),
                str(w.skill_count) if w.skill_count else "[dim]\u00b7[/dim]",
            )
        self.print(table)
        self.print(
            "[dim]Legend:[/dim] "
            "[bold green]OK[/bold green]=exists  "
            "[bold blue]NEW[/bold blue]=not created yet  "
            "[bold yellow]EPH[/bold yellow]=ephemeral (tmp per run)"
        )

    # ------------------------------------------------------------------
    # Workspace path (ws show)
    # ------------------------------------------------------------------

    def workspace_path(self, path: Path) -> None:
        """Print the absolute path of a workspace."""
        self.con.print(str(path))

    # ------------------------------------------------------------------
    # Workspace lifecycle messages (ws new, rm)
    # ------------------------------------------------------------------

    def workspace_ready(self, path: Path) -> None:
        """Confirm workspace creation."""
        self.success(f"\u2713 workspace ready: [bold]{path}[/bold]")

    def workspace_reset(self, path: Path) -> None:
        """Confirm workspace reset."""
        self.warn(f"\u21bb reset: [bold]{path}[/bold]")

    def workspace_deleted(self, name: str) -> None:
        """Confirm workspace deletion."""
        self.warn(f"deleted workspace {name!r}")

    # ------------------------------------------------------------------
    # File generation (file gen, file skills)
    # ------------------------------------------------------------------

    def configs_generated(self, result: GeneratedConfigsResult) -> None:
        """Print success message for config generation."""
        self.success(
            f"configs generated → {result.get('target_dir', '?')} "
            f"({result.get('files_written', 0)} files)"
        )

    def skills_generated(self, result: GeneratedSkillsResult) -> None:
        """Print success message for skills generation."""
        self.success(
            f"skills generated → {result.get('target_dir', '?')} "
            f"({result.get('skills_written', 0)} skills)"
        )

    # ------------------------------------------------------------------
    # File edit (file edit)
    # ------------------------------------------------------------------

    def file_content(self, content: str) -> None:
        """Print file content to stdout."""
        self.con.print(content)

    def file_written(self, path: str, bytes_val: int) -> None:
        """Confirm file write."""
        self.success(f"written {path!r} ({bytes_val} bytes)")

    def file_edit_mutual_exclusive(self) -> None:
        """Error when both --read and --write are given."""
        self.error("use --read or --write, not both")

    def file_edit_no_action(self) -> None:
        """Error when neither --read nor --write is given."""
        self.error("use --read or --write")

    # ------------------------------------------------------------------
    # MCP (mcp show, policy, toggle, refresh, tools)
    # ------------------------------------------------------------------

    def mcp_config_panel(
        self, workspace_id: str, policy: str, server_count: int,
    ) -> None:
        """Render the MCP workspace config summary panel."""
        meta = Table.grid(padding=(0, 2))
        meta.add_column(style="dim", justify="right")
        meta.add_column()
        meta.add_row("workspace_id", workspace_id)
        meta.add_row("policy", f"[bold]{policy}[/bold]")
        meta.add_row("project_servers", str(server_count))
        self.print(Panel(meta, title="MCP workspace config", border_style="cyan"))

    def mcp_server_overrides_table(self, overrides: Sequence[WorkspaceMcpOverrideRow]) -> None:
        """Render the server overrides table."""
        if not overrides:
            self.no_server_overrides()
            return

        stable = Table(header_style="bold green", padding=(0, 1))
        stable.add_column("Server", style="bold")
        stable.add_column("Enabled", justify="center")
        stable.add_column("Changelog", style="dim")
        stable.add_column("Updated at", style="dim")
        for o in overrides:
            enabled = "[green]\u2713[/green]" if o.get("enabled") else "[red]\u2717[/red]"
            stable.add_row(
                str(o.get("server_name", "")),
                enabled,
                str(o.get("changelog") or ""),
                str(o.get("created_at") or ""),
            )
        self.print(Panel(stable, title="Server overrides", border_style="green"))

    def mcp_tool_overrides_table(self, overrides: Sequence[WorkspaceMcpToolOverrideRow]) -> None:
        """Render the tool overrides table."""
        ttable = Table(header_style="bold magenta", padding=(0, 1))
        ttable.add_column("Server", style="bold")
        ttable.add_column("Tool")
        ttable.add_column("Enabled", justify="center")
        for o in overrides:
            enabled = "[green]\u2713[/green]" if o.get("enabled") else "[red]\u2717[/red]"
            ttable.add_row(
                str(o.get("server_name", "")), str(o.get("tool_name", "")), enabled,
            )
        self.print(Panel(ttable, title="Tool overrides", border_style="magenta"))

    def no_server_overrides(self) -> None:
        """Print empty-state message for no server overrides."""
        self.dim("No server overrides.")

    def mcp_policy_set(self, policy: str, workspace_id: str) -> None:
        """Confirm policy update."""
        self.success(f"\u2713 policy set to [bold]{policy}[/bold] for workspace {workspace_id!r}")

    def invalid_policy(self, error: str) -> None:
        """Print invalid-policy error."""
        self.error(f"Invalid policy. {error}")

    def mcp_toggle(self, action: str, server_name: str, workspace_id: str) -> None:
        """Confirm MCP server toggle."""
        self.success(
            f"\u2713 server [bold]{server_name}[/bold] {action} for workspace {workspace_id!r}"
        )

    def mcp_cache_invalidated(self, name: str) -> None:
        """Confirm cache invalidation for a server."""
        self.success(f"\u2713 cache invalidated: {name}")

    def no_mcp_cache(self, name: str) -> None:
        """Print no-cache state for a server."""
        self.dim(f"no cache for: {name}")

    def no_mcp_servers(self, workspace_id: str) -> None:
        """Print empty-state for no servers in workspace."""
        self.warn(f"No servers to refresh for workspace {workspace_id!r}.")

    def no_mcp_tools(self, workspace_id: str) -> None:
        """Print empty-state for no MCP tools in workspace."""
        self.dim(f"no MCP tools for workspace {workspace_id!r}")

    def mcp_tools_table(self, result: WorkspaceMcpToolsResult, workspace_id: str) -> None:
        """Render the available MCP tools table for a workspace."""
        if not result:
            self.no_mcp_tools(workspace_id)
            return

        groups_raw = result.get("groups")
        if not groups_raw or not isinstance(groups_raw, list):
            self.no_mcp_tools(workspace_id)
            return

        table = Table(title=f"MCP Tools — {workspace_id}", header_style="bold cyan")
        table.add_column("Group", style="bold")
        table.add_column("Tools", style="cyan")
        table.add_column("Kind")
        table.add_column("Active", justify="center")
        for g in groups_raw:
            if isinstance(g, dict):
                tool_names = g.get("tools", [])
                table.add_row(
                    str(g.get("name", "")),
                    ", ".join(str(t) for t in tool_names),
                    str(g.get("kind", "")),
                    self.check(bool(g.get("active"))),
                )
        self.print(table)

    # ------------------------------------------------------------------
    # Permissions (perm get, set)
    # ------------------------------------------------------------------

    def permissions_view(self, result: PermissionsView, name: str) -> None:
        """Render permissions as a JSON-syntax panel."""
        self.print(
            Panel(
                Syntax(
                    _json.dumps(result, indent=2, default=str),
                    "json",
                    theme="ansi_dark",
                ),
                title=f"Permissions — {name}",
            )
        )

    def permissions_set(self, name: str) -> None:
        """Confirm permissions update."""
        self.success(f"permissions updated for {name!r}")

    def invalid_json(self, error: str) -> None:
        """Print JSON parse error."""
        self.error(f"invalid JSON: {error}")

    # ------------------------------------------------------------------
    # Resource bindings (res ls, set, check)
    # ------------------------------------------------------------------

    def file_bindings_table(self, rows: Sequence[WorkspaceFileBindingRow], workspace_id: str) -> None:
        """Render workspace file bindings table."""
        if not rows:
            self.no_file_bindings(workspace_id)
            return

        table = Table(
            title=f"Workspace file bindings — {workspace_id}",
            title_style="bold",
            header_style="bold cyan",
            padding=(0, 1),
        )
        table.add_column("Order", style="dim")
        table.add_column("Target path", style="bold")
        table.add_column("Resource ID", style="dim")
        table.add_column("Mode", style="cyan")
        table.add_column("On conflict", style="dim")
        table.add_column("Pinned version", style="dim")
        for r in rows:
            table.add_row(
                str(r.get("display_order", 0)),
                str(r.get("target_path") or "—"),
                str(r.get("resource_id", "")),
                str(r.get("materialize_mode") or "copy"),
                str(r.get("on_conflict") or "error"),
                str(r.get("pinned_version_id") or "—"),
            )
        self.print(table)

    def no_file_bindings(self, workspace_id: str) -> None:
        """Print empty-state for no file bindings."""
        self.warn(f"No file bindings for workspace {workspace_id!r}.")

    def file_binding_set(
        self, workspace_id: str, path: str, resource_slug: str, mode: str,
    ) -> None:
        """Confirm file binding upsert."""
        self.success(
            f"\u2713 binding set: workspace=[bold]{workspace_id}[/bold] "
            f"path=[bold]{path}[/bold] → {resource_slug} (mode={mode})"
        )

    def resource_not_found(self, resource_slug: str) -> None:
        """Error for missing resource."""
        self.error(f"Resource not found: {resource_slug!r}")

    def reason_required(self) -> None:
        """Error when --reason is too short."""
        self.error("--reason must be at least 3 characters")

    def resources_resolution_table(
        self,
        entries: Sequence[MaterializeDryRunEntry],
        workspace_id: str,
        *,
        conflicts: Sequence[MaterializeConflict] | None = None,
    ) -> None:
        """Render dry-run resource resolution table."""
        if not entries:
            self.warn(f"No workspace resource bindings for {workspace_id!r}.")
            return

        table = Table(
            title=f"Dry run — {workspace_id}",
            title_style="bold",
            header_style="bold cyan",
            padding=(0, 1),
        )
        table.add_column("Target path", style="bold")
        table.add_column("Resource ID", style="dim")
        table.add_column("Version ID", style="dim")
        table.add_column("Mode", style="cyan")
        table.add_column("Files", justify="right", style="magenta")
        for r in entries:
            table.add_row(
                str(r.get("target_path") or "—"),
                str(r.get("resource_id", "")),
                str(r.get("version_id", "")),
                str(r.get("materialize_mode") or "copy"),
                str(r.get("file_count", 0)),
            )
        self.print(table)
        self.dim(f"{len(entries)} binding(s) would be materialized.")
        if conflicts:
            self.warn(f"{len(conflicts)} conflict(s) detected:")
            for c in conflicts:
                self.warn(f"  {c.get('issue', c)}")

    # ------------------------------------------------------------------
    # Skills (skill ls, show)
    # ------------------------------------------------------------------

    def skills_list(self, skills: Sequence[SkillListItem]) -> None:
        """Render a list of skill names and descriptions."""
        if not skills:
            self.dim("no skills")
            return

        for s in skills:
            name = s.get("name", "?")
            desc = str(s.get("description", ""))
            self.con.print(
                f"[bold]{name}[/bold]"
                + (f"  [dim]{desc}[/dim]" if desc else "")
            )

    def skill_content(self, content: str) -> None:
        """Render skill content with markdown syntax highlighting."""
        if content:
            self.syntax(content, "markdown", theme="ansi_dark")
        else:
            self.dim("empty skill")

    def skill_not_found(self, skill_name: str) -> None:
        """Error for missing skill."""
        self.error(f"skill {skill_name!r} not found")

    # ------------------------------------------------------------------
    # Shared error / empty-state messages
    # ------------------------------------------------------------------

    def workspace_not_found(self, name: str) -> None:
        """Error for missing workspace."""
        self.error(f"workspace {name!r} not found")
