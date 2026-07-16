"""System CLI renderer — typed output methods for system commands."""

from __future__ import annotations

from agentbox.core.data.payload_types import GrantConfig, ResolvedHostEnv

import json as _json
from collections.abc import Sequence

from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from agentbox.cli.shared.render import Renderer
from agentbox.core.service import (
    DoctorCheck,
    EnvDocRow,
    HostEnvCallLogRow,
    HostEnvProfileRow,
    McpServerSpec,
    AgentHostEnvGrantRow,
    ApiTokenRow,
)


class SystemRenderer(Renderer):
    """Typed render methods for system contracts — formatting lives here, never in command bodies."""

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def settings_sections_list(self, sections: list[str]) -> None:
        """Print a plain list of settings section names."""
        if not sections:
            self.dim("no settings sections")
            return
        for s in sections:
            self.print(f"[bold]{s}[/bold]")

    def settings_section_view(self, section: str, data: dict) -> None:
        """Print a settings section as a JSON panel."""
        self.print(
            Panel(
                Syntax(_json.dumps(data, indent=2, default=str), "json", theme="ansi_dark"),
                title=f"Settings — {section}",
            )
        )

    def settings_patched(self, section: str) -> None:
        """Print confirmation after patching a settings section."""
        self.success(f"patched section {section!r}")

    # ------------------------------------------------------------------
    # Tokens
    # ------------------------------------------------------------------

    def tokens_table(self, items: Sequence[ApiTokenRow]) -> None:
        """Render a table of API tokens."""
        if not items:
            self.dim("no tokens")
            return

        table = self.table("API Tokens", "ID", "Name", "Environment", "Created")
        for t in items:
            table.add_row(
                t["id"][:12],
                t.get("name", ""),
                t.get("environment", ""),
                t.get("created_at", ""),
            )
        self.print(table)

    def token_created(self, token_id: str, environment: str, secret: str) -> None:
        """Print confirmation for a created token, including the secret."""
        self.success(f"created token {token_id!r} for environment {environment!r}")
        self.print(f"[bold yellow]secret (save this):[/bold yellow] {secret}")

    def token_rotated(self, token_id: str, secret: str) -> None:
        """Print confirmation for a rotated token, including the new secret."""
        self.success(f"rotated token {token_id!r}")
        self.print(f"[bold yellow]new secret (save this):[/bold yellow] {secret}")

    def token_not_found(self, token_id: str) -> None:
        """Print error when a token is not found."""
        self.error(f"token {token_id!r} not found")

    def token_deleted(self, token_id: str) -> None:
        """Print confirmation after deleting a token."""
        self.warn(f"deleted token {token_id!r}")

    # ------------------------------------------------------------------
    # MCP servers (manifest MCP)
    # ------------------------------------------------------------------

    def mcp_servers_table(
        self,
        rows: Sequence[tuple[str, str, str, str | None, bool, str | None]],
    ) -> None:
        """Render a table of MCP servers with cached health info.

        Each row: ``(name, transport, endpoint, tool_count, is_cached, last_sync)``.
        """
        if not rows:
            self.warn("No MCP servers configured.")
            return

        table = self.table(
            "MCP Servers",
            "Server", "Transport", "Endpoint / Command", "Tools", "Status", "Last sync",
        )
        for name, transport, endpoint, tool_count, is_cached, last_sync in rows:
            table.add_row(
                name,
                transport,
                endpoint,
                str(tool_count) if tool_count is not None else "?",
                "[green]ok[/green]" if is_cached else "[dim]unknown[/dim]",
                last_sync or self.na(""),
            )
        self.print(table)

    # ------------------------------------------------------------------
    # Project MCP
    # ------------------------------------------------------------------

    def project_mcp_table(self, servers: list[McpServerSpec]) -> None:
        """Render a table of project-level MCP servers."""
        if not servers:
            self.dim("no project MCP servers configured")
            return

        table = self.table("Project MCP Servers", "Name", "URL", "Transport", "Command")
        for s in servers:
            url = s.url or s.command
            if url and isinstance(url, list):
                url = " ".join(url)
            table.add_row(
                s.name,
                str(url or self.na("")),
                s.transport or "http",
                " ".join(s.command) if s.command else self.na(""),
            )
        self.print(table)

    def project_mcp_removed(self, name: str) -> None:
        """Print confirmation after removing an MCP server."""
        self.warn(f"removed MCP server {name!r}")

    def project_mcp_saved(self, name: str) -> None:
        """Print confirmation after saving an MCP server."""
        self.success(f"saved MCP server {name!r}")

    # ------------------------------------------------------------------
    # Env doc
    # ------------------------------------------------------------------

    def env_doc_no_doc(self, workspace_id: str) -> None:
        """Print warning when no active env doc exists."""
        self.warn(f"No active env doc for workspace {workspace_id!r}.")

    def env_doc_show_view(
        self, doc: EnvDocRow, workspace_id: str, content_json: str
    ) -> None:
        """Render the full env doc with metadata and content panels."""
        meta = Table.grid(padding=(0, 2))
        meta.add_column(style="dim", justify="right")
        meta.add_column()
        meta.add_row("id", doc["id"])
        meta.add_row("version_number", str(doc["version_number"]))
        meta.add_row(
            "is_draft",
            "[yellow]draft[/yellow]" if doc.get("is_draft") else "[green]published[/green]",
        )
        meta.add_row("changelog", doc.get("changelog") or self.na(""))
        meta.add_row("created_at", doc.get("created_at") or self.na(""))
        self.print(Panel(meta, title=f"Env doc — {workspace_id}", border_style="cyan"))

        self.print(
            Panel(
                Syntax(content_json, "json", theme="ansi_dark"),
                title="Content",
                border_style="green",
            )
        )

    def env_doc_versions_table(self, rows: Sequence[EnvDocRow], workspace_id: str) -> None:
        """Render a table of env doc versions."""
        if not rows:
            self.warn(f"No env doc versions for workspace {workspace_id!r}.")
            return

        table = self.table(
            f"Env doc versions — {workspace_id}",
            "#", "ID", "Draft", "Changelog", "Created at",
        )
        for v in rows:
            draft = (
                "[yellow]draft[/yellow]"
                if v.get("is_draft")
                else "[green]published[/green]"
            )
            table.add_row(
                str(v["version_number"]),
                v["id"],
                draft,
                v.get("changelog") or "",
                v.get("created_at") or "",
            )
        self.print(table)

    def env_doc_saved(self, version_number: object, workspace_id: str) -> None:
        """Print confirmation after saving an env doc version."""
        self.success(
            f"env doc version [bold]{version_number}[/bold] saved "
            f"for workspace [bold]{workspace_id}[/bold]"
        )

    def env_doc_published(self, version_number: object, workspace_id: str) -> None:
        """Print confirmation after publishing an env doc version."""
        self.success(
            f"env doc version [bold]{version_number}[/bold] published "
            f"for workspace [bold]{workspace_id}[/bold]"
        )

    def env_doc_rolled_back(self, version_number: object, workspace_id: str) -> None:
        """Print confirmation after rolling back an env doc."""
        self.success(
            f"rolled back — new env doc version [bold]{version_number}[/bold] "
            f"for workspace [bold]{workspace_id}[/bold]"
        )

    def env_doc_preview(self, entries: object) -> None:
        """Print env doc preview as JSON."""
        self.con.print(_json.dumps(entries, indent=2, default=str))

    def env_doc_invalid_json(self, exc: Exception) -> None:
        """Print error for invalid JSON input."""
        self.error(f"Invalid JSON: {exc}")

    def env_doc_invalid_changelog(self) -> None:
        """Print error for invalid changelog."""
        self.error("--changelog must be at least 3 characters")

    # ------------------------------------------------------------------
    # Host env
    # ------------------------------------------------------------------

    def host_env_profiles_table(self, rows: Sequence[HostEnvProfileRow]) -> None:
        """Render a table of host-env profiles."""
        if not rows:
            self.warn("No host-env profiles defined.")
            return

        table = self.table(
            "Host-env profiles",
            "ID", "Name", "Description", "Created at",
        )
        for r in rows:
            table.add_row(
                r["id"],
                r["name"],
                r.get("description") or self.na(""),
                r.get("created_at") or "",
            )
        self.print(table)

    def host_env_grants_view(
        self, agent_id: str, row: AgentHostEnvGrantRow, resolved: ResolvedHostEnv
    ) -> None:
        """Render host-env grants for an agent."""
        meta = Table.grid(padding=(0, 2))
        meta.add_column(style="dim", justify="right")
        meta.add_column()
        meta.add_row("agent_id", agent_id)
        meta.add_row("profile_id", row.get("profile_id") or self.na(""))
        meta.add_row("changelog", row.get("changelog") or self.na(""))
        meta.add_row("created_at", row.get("created_at") or self.na(""))
        self.print(
            Panel(meta, title=f"Host-env grant — {agent_id}", border_style="cyan")
        )

        grants_raw = resolved.get("grants")
        grants: dict[str, GrantConfig] = grants_raw if isinstance(grants_raw, dict) else {}
        if grants:
            gtable = self.table("Capability", "Value")
            gtable.title = None
            for cap, val in sorted(grants.items()):
                gtable.add_row(cap, str(val))
            gtable.title = "Resolved grants"
            gtable.title_style = "bold"
            self.print(Panel(gtable, title="Resolved grants", border_style="green"))
        else:
            self.dim("No grants resolved.")

    def host_env_no_grants(self, workspace_id: str) -> None:
        """Print warning when no host-env grant exists for a workspace."""
        self.warn(f"No host-env grant for workspace {workspace_id!r}.")

    def host_env_audit_table(self, rows: Sequence[HostEnvCallLogRow], run_id: str) -> None:
        """Render a table of host-env call audit log for a run."""
        if not rows:
            self.warn(f"No host-env calls recorded for run {run_id!r}.")
            return

        table = self.table(
            f"Host-env audit — run {run_id}",
            "ID", "Workspace", "Capability", "Status", "Error", "Created at",
        )
        for r in rows:
            status = r.get("status") or ""
            status_display = (
                "[green]ok[/green]" if status == "ok" else f"[red]{status}[/red]"
            )
            table.add_row(
                r["id"],
                r.get("workspace_id") or self.na(""),
                r["capability"],
                status_display,
                r.get("error") or "",
                r.get("created_at") or "",
            )
        self.print(table)

    # ------------------------------------------------------------------
    # Doctor
    # ------------------------------------------------------------------

    def doctor_report(self, checks: Sequence[DoctorCheck]) -> None:
        """Render a table of doctor check results."""
        table = self.table("Agentbox Doctor", "Status", "Check", "Detail")
        for c in checks:
            status = "[green]OK[/green]" if c.ok else "[red]FAIL[/red]"
            table.add_row(status, c.name, c.detail)
        self.print(table)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health_unreachable(self) -> None:
        """Print error when the server is not reachable."""
        self.error("server is not reachable")

    def health_error(self, message: str) -> None:
        """Print a generic health check error."""
        self.error(f"health check failed: {message}")

    def health_status_json(self, data: dict) -> None:
        """Print health check response as JSON."""
        self.con.print(_json.dumps(data, indent=2, default=str))

    def health_status_view(self, data: dict) -> None:
        """Print health check response as formatted lines."""
        status = data.get("status", "unknown")
        color = "green" if status == "ok" else "red"
        self.print(f"health: [{color}]{status}[/{color}]")
        if "version" in data:
            self.print(f"version: {data['version']}")
        if "db" in data:
            self.print(f"db: {data['db']}")
        if "uptime" in data:
            self.print(f"uptime: {data['uptime']}")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
