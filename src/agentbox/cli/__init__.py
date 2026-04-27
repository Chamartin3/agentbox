"""agentbox CLI — restructured into per-group modules.

Entry point: ``agentbox.cli:app`` (wired in pyproject.toml).
"""

from agentbox.cli.agent import agent_app
from agentbox.cli.cfg import cfg_app
from agentbox.cli.mcp import mcp_app
from agentbox.cli.mf import mf_app
from agentbox.cli.migrate import migrate_app
from agentbox.cli.root import app, register_backward_compat
from agentbox.cli.runs import runs_app
from agentbox.cli.versioning import versioning_app
from agentbox.cli.ws import ws_app

app.add_typer(agent_app, name="agent")
app.add_typer(ws_app, name="ws")
app.add_typer(runs_app, name="runs")
app.add_typer(cfg_app, name="cfg")
app.add_typer(mf_app, name="mf")
app.add_typer(mcp_app, name="mcp")
app.add_typer(migrate_app, name="migrate")
app.add_typer(versioning_app, name="versioning")

register_backward_compat()

__all__ = ["app"]
