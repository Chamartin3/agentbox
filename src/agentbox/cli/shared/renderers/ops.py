"""Ops CLI renderer — typed output methods for ops commands."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table as RichTable
from rich.text import Text
from rich.tree import Tree

from agentbox.cli.shared.constants import JsonValue
from agentbox.cli.shared.render import Renderer

from agentbox.core.config import Settings
from agentbox.core.data.workenv import RenderedFile
from agentbox.core.service import AgentDef


class OpsRenderer(Renderer):
    """Typed render methods for ops contracts — formatting lives here, never in command bodies."""

    # ------------------------------------------------------------------
    # Structural helpers (used by multiple commands)
    # ------------------------------------------------------------------

    def grid(self) -> RichTable:
        """Return a two-column right-aligned grid for key-value layouts."""
        t = RichTable.grid(padding=(0, 2))
        t.add_column(style="dim", justify="right")
        t.add_column()
        return t

    def action_text(self, action: str, style: str) -> Text:
        """Return a styled Text for table action cells."""
        return Text(action, style=style)

    def tree(self, tree: Tree) -> None:
        """Print a Rich Tree (built by the command)."""
        self.con.print(tree)

    # ------------------------------------------------------------------
    # cfg
    # ------------------------------------------------------------------

    def cfg_tree(
        self,
        settings: Settings,
        ws_resolve: Callable[..., tuple[Path, bool]],
        agents: Sequence[AgentDef],
    ) -> None:
        """Show all important paths as a Rich tree."""
        tree = Tree(f"[bold]{settings.project_root}[/bold]")

        def _add(p: Path, parent: Tree, label: str | None = None) -> None:
            lbl = label or p.name
            if p.exists():
                size = p.stat().st_size if p.is_file() else 0
                suffix = f" ({size} bytes)" if size else ""
                parent.add(f"[green]{lbl}[/green]{suffix}")
            else:
                parent.add(f"[dim]{lbl}[/dim] · missing")

        _add(settings.manifest_path, tree, "manifest.toml")
        if settings.agents_dir:
            _add(settings.agents_dir, tree, "agents.d/")
        if settings.prompts_dir:
            _add(settings.prompts_dir, tree, "prompts.d/")
        if settings.skills_dir:
            _add(settings.skills_dir, tree, "skills.d/")
        if settings.outputs_dir:
            _add(settings.outputs_dir, tree, "outputs/")

        ws_branch = tree.add("[bold]workspaces/[/bold]")
        for a in agents:
            path, _eph = ws_resolve(a, settings)
            _add(path, ws_branch, a.id + (" [yellow](ephemeral)[/yellow]" if _eph else ""))

        data = tree.add("[bold]/data[/bold]")
        _add(settings.db_path, data, "agentbox.sqlite")
        _add(settings.runs_dir, data, "runs/")
        _add(settings.sessions_dir, data, "sessions/")
        _add(settings.mcp_cache_dir, data, "mcp_cache/")

        self.con.print(tree)

    # ------------------------------------------------------------------
    # migrate
    # ------------------------------------------------------------------

    def migration_table(
        self, title: str, results: dict[str, dict[str, bool]]
    ) -> None:
        """Render a ws-perms migration results table."""
        table = RichTable(
            title=title,
            title_style="bold",
            header_style="bold cyan",
            padding=(0, 1),
        )
        table.add_column("Workspace", style="bold")
        table.add_column("Migrated", justify="center")
        table.add_column("Backup", justify="center")

        for ws_name, result in results.items():
            migrated = (
                Text("✓", style="green")
                if result["migrated"]
                else Text("·", style="dim")
            )
            backed_up = (
                Text("✓", style="green")
                if result["backed_up"]
                else Text("·", style="dim")
            )
            table.add_row(ws_name, migrated, backed_up)

        self.con.print(table)

    def migration_import_table(self, title: str) -> RichTable:
        """Create a table structure for import-manifest results."""
        table = RichTable(
            title=title,
            title_style="bold",
            header_style="bold cyan",
            padding=(0, 1),
        )
        table.add_column("Section")
        table.add_column("Key", style="bold")
        table.add_column("Action", justify="center")
        return table

    def migration_composition_table(self, summary: Mapping[str, int]) -> None:
        """Render a composition migration summary table."""
        table = RichTable(
            title="Composition Migration", header_style="bold cyan", padding=(0, 2)
        )
        table.add_column("Metric", style="bold")
        table.add_column("Count", justify="right")
        for k, v in summary.items():
            table.add_row(k, str(v))
        self.con.print(table)

    # ------------------------------------------------------------------
    # resources: repo
    # ------------------------------------------------------------------

    def resource_table(self, rows: Sequence[Mapping[str, JsonValue]]) -> None:
        """Render the resources list table."""
        table = RichTable(
            title="Resources", title_style="bold", header_style="bold cyan", padding=(0, 1)
        )
        table.add_column("Slug", style="bold")
        table.add_column("Type", style="cyan")
        table.add_column("Name")
        table.add_column("Status", style="dim")
        table.add_column("Active version", style="dim")
        table.add_column("Tags", style="magenta")
        for r in rows:
            table.add_row(
                str(r["slug"]),
                str(r["type"]),
                str(r.get("display_name") or ""),
                str(r.get("status") or "active"),
                str(r.get("active_version_id") or "[dim]---[/dim]"),
                str(r.get("tags") or ""),
            )
        self.con.print(table)

    def resource_detail(
        self,
        slug: str,
        resource: Mapping[str, JsonValue],
        versions: Sequence[Mapping[str, JsonValue]],
    ) -> None:
        """Render resource metadata + version history."""
        meta = self.grid()
        meta.add_row("id", str(resource["id"]))
        meta.add_row("slug", str(resource["slug"]))
        meta.add_row("type", str(resource["type"]))
        meta.add_row("name", str(resource.get("display_name") or "---"))
        meta.add_row("description", str(resource.get("description") or "---"))
        self.con.print(Panel(meta, title=f"Resource: {slug}", border_style="cyan"))

        if not versions:
            self.dim("No versions.")
            return
        self.version_table(versions)

    def version_table(self, versions: Sequence[Mapping[str, JsonValue]]) -> None:
        """Render a version list table."""
        vtable = RichTable(header_style="bold green", padding=(0, 1))
        vtable.add_column("#", style="dim")
        vtable.add_column("ID", style="dim")
        vtable.add_column("Draft", justify="center")
        vtable.add_column("Source")
        vtable.add_column("Changelog")
        vtable.add_column("Created at", style="dim")
        for v in versions:
            draft = (
                "[yellow]draft[/yellow]"
                if v.get("is_draft")
                else "[green]published[/green]"
            )
            vtable.add_row(
                str(v["version_number"]),
                str(v["id"]),
                draft,
                str(v.get("import_source") or ""),
                str(v.get("changelog") or ""),
                str(v.get("created_at") or ""),
            )
        self.con.print(vtable)

    # ------------------------------------------------------------------
    # resources: bindings
    # ------------------------------------------------------------------

    def bindings_table(
        self, agent_id: str, rows: Sequence[Mapping[str, JsonValue]]
    ) -> None:
        """Render the prompt bindings list table."""
        table = RichTable(
            title=f"Prompt bindings — {agent_id}",
            title_style="bold",
            header_style="bold cyan",
            padding=(0, 1),
        )
        table.add_column("Order", style="dim")
        table.add_column("Marker", style="bold")
        table.add_column("Resource ID", style="dim")
        table.add_column("Mode", style="cyan")
        table.add_column("Required", justify="center")
        table.add_column("Pinned version", style="dim")
        for r in rows:
            required = "[green]✓[/green]" if r.get("required") else "[dim]·[/dim]"
            table.add_row(
                str(r.get("display_order", 0)),
                str(r["marker"]),
                str(r["resource_id"]),
                str(r.get("mode") or ""),
                required,
                str(r.get("pinned_version_id") or "—"),
            )
        self.con.print(table)

    def prompt_preview(
        self,
        agent_id: str,
        rendered_prompt: str,
        warnings: Sequence[str],
        unresolved_markers: Sequence[str],
        snapshot_rows: Sequence[tuple[str, str, str, str]] | None,
    ) -> None:
        """Render a resolved prompt preview with syntax highlighting and binding snapshot."""
        self.con.print(
            Panel(
                Syntax(rendered_prompt, "markdown", theme="ansi_dark"),
                title=f"Resolved prompt — {agent_id}",
                border_style="cyan",
            )
        )

        for w in warnings:
            self.warn(f"warning: {w}")
        if unresolved_markers:
            self.warn(f"unresolved markers: {', '.join(unresolved_markers)}")

        if snapshot_rows:
            snap_table = RichTable(header_style="bold magenta", padding=(0, 1))
            snap_table.add_column("Marker")
            snap_table.add_column("Resource ID", style="dim")
            snap_table.add_column("Mode")
            snap_table.add_column("Version", style="dim")
            for marker, resource_id, mode, version_id in snapshot_rows:
                snap_table.add_row(marker, resource_id, mode, version_id)
            self.con.print(Panel(snap_table, title="Binding snapshot", border_style="green"))

    # ------------------------------------------------------------------
    # shell
    # ------------------------------------------------------------------

    def shell_banner(
        self,
        agent: str,
        workspace_path: Path,
        is_ephemeral: bool,
        creds: str | None,
        env_doc_rendered: bool,
    ) -> None:
        """Print the shell banner."""
        self.con.print("━" * 60)
        self.con.print(f"[bold]agentbox shell[/bold] — [cyan]{agent}[/cyan]")
        self.con.print("━" * 60)
        self.con.print(
            f"  workdir:   {workspace_path}{'  (ephemeral)' if is_ephemeral else ''}"
        )
        self.con.print(
            f"  env-doc:   {'rendered (CLAUDE.md / AGENTS.md)' if env_doc_rendered else 'none'}"
        )
        self.con.print(f"  creds:     {creds or 'default'}")
        self.con.print()
        self.con.print("  Native config (.mcp.json / .claude / opencode.json) is in cwd.")
        self.con.print("  Exit the shell to return.")
        self.con.print()

    def launch_banner(
        self,
        agent: str | None,
        runner: str,
        model: str | None,
        workspace_path: Path,
        is_ephemeral: bool,
        creds: str | None,
    ) -> None:
        """Print the launch banner."""
        mode = ("ephemeral (tmp)" if is_ephemeral
                else f"workspace ({workspace_path})")
        self.con.print("━" * 50)
        label = f"[cyan]{agent}[/cyan]" if agent else "[dim]<no agent>[/dim]"
        self.con.print(f"[bold]agentbox launch[/bold] ({runner}) — {label}")
        self.con.print("━" * 50)
        self.con.print(f"  model:  {model or '<runner default>'}")
        self.con.print(f"  mode:   {mode}")
        self.con.print(f"  creds:  {creds or 'default'}")
        self.con.print()

    # ------------------------------------------------------------------
    # workenv
    # ------------------------------------------------------------------

    def workenv_preview(self, files: Sequence[RenderedFile]) -> None:
        """Print rendered workenv files to stdout instead of writing to disk."""
        for f in files:
            self.con.print(f"\n[bold cyan]─── {f.rel_path}[/bold cyan]")
            syntax = Syntax(
                f.content,
                "json"
                if f.rel_path.suffix == ".json"
                else "yaml"
                if f.rel_path.suffix in (".yaml", ".yml")
                else "markdown",
                theme="ansi_dark",
            )
            self.con.print(syntax)

    # ------------------------------------------------------------------
    # run
    # ------------------------------------------------------------------

    def run_url_text(self, api: str, run_id: str) -> str:
        """Return a Rich-compatible URL text for a run view link."""
        return f"View: [link={api}/runs/{run_id}]{api}/runs/{run_id}[/link]"
