"""agentbox CLI — restructured into per-group modules.

Entry point: ``agentbox.cli:app`` (wired in pyproject.toml).
"""

from agentbox.cli.agent import agent_app
from agentbox.cli.cfg import cfg_app
from agentbox.cli.env_doc import env_doc_app
from agentbox.cli.host_env import host_env_app
from agentbox.cli.mcp import mcp_app
from agentbox.cli.mcp_workspace import mcp_workspace_app
from agentbox.cli.mf import mf_app
from agentbox.cli.migrate import migrate_app
from agentbox.cli.prompt_bindings import prompt_bindings_app
from agentbox.cli.resource import resource_app
from agentbox.cli.root import app, register_backward_compat
from agentbox.cli.runner_profiles import runner_profile_app, runner_provider_app
from agentbox.cli.runs import runs_app
from agentbox.cli.versioning import versioning_app
from agentbox.cli.workspace_resources import workspace_resources_app
from agentbox.cli.ws import ws_app

app.add_typer(agent_app, name="agent")
app.add_typer(ws_app, name="ws")
app.add_typer(runs_app, name="runs")
app.add_typer(cfg_app, name="cfg")
app.add_typer(mf_app, name="mf")
app.add_typer(mcp_app, name="mcp")
app.add_typer(migrate_app, name="migrate")
app.add_typer(versioning_app, name="versioning")
app.add_typer(runner_profile_app, name="runner-profile")
app.add_typer(runner_provider_app, name="runner-provider")
app.add_typer(resource_app, name="resource")
app.add_typer(prompt_bindings_app, name="prompt-bindings")
app.add_typer(workspace_resources_app, name="workspace-resources")
app.add_typer(env_doc_app, name="env-doc")
app.add_typer(mcp_workspace_app, name="mcp-workspace")
app.add_typer(host_env_app, name="host-env")

register_backward_compat()

__all__ = ["app"]
