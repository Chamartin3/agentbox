"""agentbox CLI — restructured into per-group subpackages.

Top-level command groups mirror the API layout under
``src/agentbox/api/``: ``agents``, ``runs``, ``runners``,
``workspaces``, ``resources``, ``analytics``, ``system``, ``ops``.

Entry point: ``agentbox.cli:app`` (wired in pyproject.toml).
"""

from __future__ import annotations

from agentbox.cli.agents import app as agents_app
from agentbox.cli.feedback import app as feedback_app
from agentbox.cli.ops import app as ops_app
from agentbox.cli.resources import app as resources_app
from agentbox.cli.root import app
from agentbox.cli.engines import app as runners_app
from agentbox.cli.runs import app as runs_app
from agentbox.cli.system import app as system_app
from agentbox.cli.workspaces import app as workspaces_app

app.add_typer(agents_app, name="agents")
app.add_typer(runs_app, name="runs")
app.add_typer(runners_app, name="runners")
app.add_typer(workspaces_app, name="workspaces")
app.add_typer(resources_app, name="resources")
app.add_typer(feedback_app, name="feedback")
app.add_typer(system_app, name="system")
app.add_typer(ops_app, name="ops")

__all__ = ["app"]
