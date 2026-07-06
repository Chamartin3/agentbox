"""Agent CLI renderer — typed output methods for agent commands.

Formatting lives here, never in command bodies. Command modules call
these methods on ``ctx.obj.render.agent`` with pre-fetched data.
"""

from __future__ import annotations

import json as _json
from collections.abc import Sequence

from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from agentbox.cli.shared.constants import JsonValue
from agentbox.cli.shared.render import Renderer
from agentbox.core.data.payload_types import AgentDiffResult, AgentValidationResult
from agentbox.core.service import AgentDef, McpServerSpec, ToolSpec


class AgentRenderer(Renderer):
    """Typed render methods for agent contracts — formatting lives here, never in command bodies."""

    # ------------------------------------------------------------------
    # Agent listing
    # ------------------------------------------------------------------

    def agents_table(self, rows: Sequence[dict[str, object]]) -> None:
        """Render a table of agents with ID, Runner, Model, Session, Workspace, Description."""
        if not rows:
            self.warn("No agents registered.")
            return

        table = self.table(
            "Agents",
            "ID", "Runner", "Model", "Session", "Workspace", "Description",
        )
        for a in rows:
            table.add_row(
                str(a.get("id", "")),
                str(a.get("runner_kind", "")),
                str(a.get("model", "")),
                str(a.get("session_mode", "")),
                str(a.get("workspace", "")),
                str(a.get("description") or ""),
            )
        self.print(table)

    def agents_json(self, rows: Sequence[dict[str, object]]) -> None:
        """Render agents as JSON."""
        self.con.print(_json.dumps(list(rows), indent=2))

    # ------------------------------------------------------------------
    # Agent detail
    # ------------------------------------------------------------------

    def agent_meta_panel(self, agent: AgentDef) -> None:
        """Render agent metadata panel."""
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="dim", justify="right")
        grid.add_column()
        grid.add_row("id", agent.id)
        grid.add_row("description", agent.description or "\u2014")
        grid.add_row(
            "source_format",
            agent.source_format.value if agent.source_format else "\u2014",
        )
        grid.add_row(
            "source_path",
            str(agent.source_path) if agent.source_path else "\u2014",
        )
        grid.add_row("tags", ", ".join(agent.tags) if agent.tags else "\u2014")
        self.print(Panel(grid, title="Meta", border_style="cyan"))

    def agent_runner_panel(self, agent: AgentDef) -> None:
        """Render agent runner panel."""
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="dim", justify="right")
        grid.add_column()
        grid.add_row("kind", agent.runner.kind)
        grid.add_row("timeout", f"{agent.runner.timeout_seconds}s")
        grid.add_row(
            "allowed_tools",
            ", ".join(agent.runner.allowed_tools) if agent.runner.allowed_tools else "\u2014",
        )
        grid.add_row("mcp_config_path", agent.runner.mcp_config_path or "\u2014")
        self.print(Panel(grid, title="Runner", border_style="green"))

    def agent_profile_panel(self, profile: dict[str, object] | None) -> None:
        """Render runner profile panel for an agent."""
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="dim", justify="right")
        grid.add_column()
        if profile is None:
            grid.add_row("bound profile", "[dim](none \u2014 system default)[/dim]")
        else:
            grid.add_row("id", str(profile.get("id", "")))
            grid.add_row("name", str(profile.get("name", "")))
            grid.add_row("backend", str(profile.get("backend", "")))
            grid.add_row("provider", str(profile.get("provider") or "\u2014"))
            grid.add_row("model", str(profile.get("model") or "\u2014"))
        self.print(Panel(grid, title="Runner profile", border_style="green"))

    def agent_workspace_panel(self, agent: AgentDef) -> None:
        """Render workspace panel for an agent."""
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style="dim", justify="right")
        grid.add_column()
        ws_display = (
            "[yellow]<ephemeral>[/yellow]"
            if agent.workspace == "<ephemeral>"
            else (agent.workspace or "[dim]auto[/dim]")
        )
        grid.add_row("workspace", ws_display)
        grid.add_row("session_mode", agent.session_mode)
        grid.add_row("headless", str(agent.headless))
        grid.add_row("claude_agent", str(agent.claude_agent))
        self.print(Panel(grid, title="Workspace", border_style="blue"))

    def agent_mcp_servers_panel(self, servers: Sequence[McpServerSpec] | None) -> None:
        """Render MCP servers panel for an agent."""
        if not servers:
            return
        mcp_grid = Table.grid(padding=(0, 2))
        mcp_grid.add_column(style="dim")
        mcp_grid.add_column()
        for s in servers:
            mcp_grid.add_row(s.name, s.url or " ".join(s.command or []))
        self.print(Panel(mcp_grid, title="MCP Servers", border_style="yellow"))

    # ------------------------------------------------------------------
    # Version listing
    # ------------------------------------------------------------------

    def versions_table(
        self,
        versions: Sequence[dict[str, object]],
        agent_id: str,
        *,
        active_id: JsonValue = None,
        latest_version: JsonValue = None,
        active_version: JsonValue = None,
    ) -> None:
        """Render version history table for an agent."""
        if not versions:
            self.warn("No versions.")
            return

        table = self.table(
            f"Versions \u2014 {agent_id}",
            "#", "Author", "Changelog", "Active", "Created",
        )
        for v in versions:
            active_marker = "\u2713" if v.get("id") == active_id else "\u00b7"
            table.add_row(
                str(v.get("version", "")),
                str(v.get("author", "")),
                str(v.get("changelog", ""))[:60],
                active_marker,
                str(v.get("created_at", "")),
            )
        self.print(table)
        self.dim(
            f"latest: v{latest_version if latest_version else '-'}  "
            f"active: v{active_version if active_version else '-'}"
        )

    def version_detail(
        self,
        version: dict[str, object],
        *,
        rating: dict[str, object] | None = None,
        comments: Sequence[dict[str, object]] | None = None,
    ) -> None:
        """Render a single version's detail with content snapshot, rating, and comments."""
        self.print(
            Panel(
                f"v{version.get('version', '')} \u2014 "
                f"{version.get('author', '')} \u2014 "
                f"{version.get('changelog', '')}",
                title=f"Version {version.get('version', '')}",
            )
        )
        self.con.print(f"created: {version.get('created_at', '')}")
        if rating:
            self.con.print(
                f"rating: [yellow]{rating['rating']}/5[/yellow] by "
                f"{rating.get('rater', '')}"
            )

        if version.get("content_snapshot"):
            try:
                parsed = _json.loads(str(version["content_snapshot"]))
                self.json(parsed)
            except (_json.JSONDecodeError, TypeError):
                self.dim(str(version["content_snapshot"])[:500])

        if comments:
            ct = Table(header_style="bold cyan")
            ct.add_column("Author")
            ct.add_column("Body")
            ct.add_column("Created")
            for c in comments:
                ct.add_row(
                    str(c.get("author", "")),
                    str(c.get("body", ""))[:80],
                    str(c.get("created_at", "")),
                )
            self.print(Panel(ct, title="Comments"))

    def version_diff(self, diff: AgentDiffResult) -> None:
        """Render version diff as JSON."""
        self.syntax(_json.dumps(diff, indent=2, default=str), "json")

    # ------------------------------------------------------------------
    # Prompt
    # ------------------------------------------------------------------

    def prompt_view(self, content: str) -> None:
        """Render prompt content with markdown syntax highlighting."""
        if not content:
            self.warn("No prompt content.")
            return
        self.syntax(content, "markdown")

    def prompt_versions_table(self, title: str, rows: Sequence[dict[str, object]], *, style: str = "bold cyan") -> None:
        """Render a table of prompt versions (committed or drafts)."""
        if not rows:
            return

        table = self.table(title, "#", "Author", "Hash", "Created")
        for v in rows:
            table.add_row(
                str(v.get("version", "")),
                str(v.get("author", "")),
                str(v.get("hash_", ""))[:8] if v.get("hash_") else "",
                str(v.get("created_at", "")),
            )
        self.print(table)

    def prompt_drafts_table(self, rows: Sequence[dict[str, object]]) -> None:
        """Render a table of prompt drafts."""
        if not rows:
            return

        table = Table(title="Drafts", header_style="bold yellow")
        table.add_column("#", style="dim", justify="right")
        table.add_column("Author")
        table.add_column("Updated")
        for v in rows:
            table.add_row(
                str(v.get("version", "")),
                str(v.get("author", "")),
                str(v.get("updated_at", "")),
            )
        self.print(table)

    # ------------------------------------------------------------------
    # Tool grants
    # ------------------------------------------------------------------

    def grants_table(self, grants: Sequence[dict[str, object]], agent_id: str) -> None:
        """Render a table of tool grants for an agent."""
        if not grants:
            self.warn("No tool grants.")
            return

        table = self.table(
            f"Tool Grants \u2014 {agent_id}",
            "Tool", "Revoked", "Changelog", "Actor", "Created",
        )
        for g in grants:
            revoked = (
                "[red]yes[/red]" if g.get("revoked_at") else "[green]no[/green]"
            )
            table.add_row(
                str(g.get("tool_name", "")),
                revoked,
                str(g.get("changelog", "")),
                str(g.get("actor", "")),
                str(g.get("created_at", "")),
            )
        self.print(table)

    def tools_table(self, specs: Sequence[ToolSpec]) -> None:
        """Render a table of available tools."""
        if not specs:
            self.warn("No tools registered.")
            return

        table = self.table("Agent Tools", "Name", "Capability", "Tags")
        for s in specs:
            table.add_row(s.name, s.capability, ", ".join(s.tags))
        self.print(table)

    def tool_detail(self, spec: ToolSpec) -> None:
        """Render full detail for a single tool."""
        self.print(
            Panel(
                f"[bold]{spec.name}[/bold]\n{spec.description}",
                title="Description",
            )
        )
        self.con.print(f"Capability: [cyan]{spec.capability}[/cyan]")
        self.con.print(f"Tags: {', '.join(spec.tags)}")

        self.print(
            Panel(
                self._syntax_str(_json.dumps(spec.input_model.model_json_schema(), indent=2), "json"),
                title="Input Schema",
            )
        )
        self.print(
            Panel(
                self._syntax_str(_json.dumps(spec.output_model.model_json_schema(), indent=2), "json"),
                title="Output Schema",
            )
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validation_report(self, result: AgentValidationResult) -> None:
        """Render inline validator config for both directions."""
        for direction in ("input", "output"):
            raw = result.get(direction)
            section: dict[str, object] = {}
            if isinstance(raw, dict):
                section = raw
            validators = section.get("validators", [])
            if validators:
                self.print(
                    Panel(
                        Syntax(
                            _json.dumps(validators, indent=2),
                            "json",
                            theme="ansi_dark",
                        ),
                        title=f"[bold]{direction}[/bold] validators",
                    )
                )
            else:
                self.dim(f"{direction}: no validators")

    # ------------------------------------------------------------------
    # Simple success messages (agent lifecycle)
    # ------------------------------------------------------------------

    def agent_created(self, agent_id: str, version: JsonValue, version_id: JsonValue) -> None:
        """Print success message for agent creation."""
        self.success(f"created {agent_id!r} v{version} (draft, version_id={version_id})")

    def agent_deleted(self, agent_id: str) -> None:
        """Print success message for agent deletion."""
        self.success(f"deleted {agent_id!r}")

    def agent_not_found(self, agent_id: str) -> None:
        """Print error for missing agent."""
        self.error(f"agent {agent_id!r} not found")

    def version_created(self, version: JsonValue, version_id: JsonValue) -> None:
        """Print success message for version creation."""
        self.success(f"created v{version} (id={version_id})")

    def draft_created(self, version: JsonValue, version_id: JsonValue) -> None:
        """Print success message for draft creation."""
        self.success(f"draft created v{version} (id={version_id})")

    def prompt_revision_created(self, version: JsonValue, version_id: JsonValue, active: bool) -> None:
        """Print success message for prompt revision."""
        self.success(f"prompt revision v{version} (id={version_id}, active={active})")

    def version_published(self, version: JsonValue, version_id: JsonValue) -> None:
        """Print success message for version publish."""
        self.success(f"published v{version} (id={version_id})")

    def version_rolled_back(self, target_version: JsonValue, new_version: JsonValue) -> None:
        """Print success message for version rollback."""
        self.success(f"rolled back to v{target_version} (new v{new_version})")

    def comment_added(self, comment_id: JsonValue) -> None:
        """Print success message for comment addition."""
        self.success(f"comment added (id={comment_id})")

    def version_rated(self, version: int, stars: int) -> None:
        """Print success message for version rating."""
        self.success(f"rated v{version} \u2192 {stars}/5")

    def agent_exported(self, base: str) -> None:
        """Print success message for agent export."""
        self.success(f"done \u2192 {base}")

    def file_added(self, name: str, file_id: JsonValue, sha256: str) -> None:
        """Print success message for file addition."""
        self.success(f"added {name!r} (file_id={file_id}, sha256={sha256[:8]})")

    def file_removed(self, file_id: int, version: int) -> None:
        """Print success message for file removal."""
        self.warn(f"removed file {file_id} from v{version}")

    def version_edit_new(self, agent_id: str, version: JsonValue) -> None:
        """Print success message for version edit."""
        self.success(
            f"new version {agent_id!r} v{version} "
            "\u2014 publish with `agent version publish`"
        )

    def prompt_updated(self, agent_id: str) -> None:
        """Print success message for prompt update."""
        self.success(f"updated agent {agent_id!r} prompt")

    def prompt_draft_saved(self, agent_id: str) -> None:
        """Print success message for prompt draft save."""
        self.success(f"saved draft for {agent_id!r}")

    def prompt_published(self, agent_id: str) -> None:
        """Print success message for prompt publish."""
        self.success(f"published {agent_id!r} prompt")

    def prompt_rolled_back(self, agent_id: str, target_version: int) -> None:
        """Print success message for prompt rollback."""
        self.success(f"rolled back to v{target_version} for {agent_id!r}")

    def tool_granted(self, tool_name: str, agent_id: str) -> None:
        """Print success message for tool grant."""
        self.success(f"granted {tool_name!r} to {agent_id!r}")

    def tool_revoked(self, tool_name: str, agent_id: str) -> None:
        """Print success message for tool revocation."""
        self.warn(f"revoked {tool_name!r} from {agent_id!r}")

    def validation_updated(self, direction: str, version: JsonValue) -> None:
        """Print success message for validation update."""
        self.success(f"updated {direction} validators \u2014 v{version}")

    def profile_bound(self, profile_id: str, agent_id: str) -> None:
        """Print success message for profile binding."""
        self.success(f"bound profile {profile_id!r} to {agent_id!r}")

    def profile_cleared(self, agent_id: str) -> None:
        """Print success for clearing profile binding."""
        self.warn(f"cleared profile binding for {agent_id!r}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _syntax_str(code: str, lexer: str) -> Syntax:
        """Return a Rich Syntax object for embedding in Panels."""
        return Syntax(code, lexer, theme="ansi_dark")