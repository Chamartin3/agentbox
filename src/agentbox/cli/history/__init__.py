"""History branch — inspect run history and view stats.

Tree (≤6 children per node):
history
├── ls                          # list runs
├── show                        # show run detail
├── cancel                      # cancel in-progress run
├── log       tail  transcript  prompt  comments  outcome
└── stat      usage  activity  runs  facets  stats
"""

from __future__ import annotations

import typer

from agentbox.cli.history.crud import register_cancel, register_ls, register_show
from agentbox.cli.history.log import log_app
from agentbox.cli.history.stat import stat_app
from agentbox.cli.shared import group_callback

app = typer.Typer(
    name="history",
    help="Inspect run history: ls, show, cancel, logs, and stats.",
    rich_markup_mode="rich",
    no_args_is_help=True,
)
app.callback()(group_callback)

register_ls(app)
register_show(app)
register_cancel(app)
app.add_typer(log_app, name="log")
log_app.callback()(group_callback)

app.add_typer(stat_app, name="stat")
stat_app.callback()(group_callback)

__all__ = ["app"]
