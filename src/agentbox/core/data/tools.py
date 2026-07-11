"""Canonical tool-name vocabulary.

A single enum that is the authoritative list of internal tool names.
Because ``CanonicalTool`` extends ``CatalogEnum`` (which extends
``StrEnum``), every member compares equal to its string value::

    CanonicalTool.FS_READ == "fs.read"  # True
    "fs.read" == CanonicalTool.FS_READ  # True

This means existing code that uses bare strings in comparisons or as
dict keys continues to work without changes — adopt incrementally.

It lives in ``core.data`` (the shapes leaf) because it is vocabulary — a
pure shape with no logic — and both the agents and engines domains name
it in their boundary views.
"""

from __future__ import annotations

from agentbox.core.data.constants import CatalogEnum


class CanonicalTool(CatalogEnum):
    """Enumerated vocabulary of all canonical internal tool names.

    Members use the ``UPPER_SNAKE_CASE`` convention; their ``value`` is
    the dot-namespaced string used on the wire and in DB config.

    Namespaces:
        - ``fs.*``           — local filesystem operations
        - ``shell.*``        — shell / process execution
        - ``http.*``         — outbound HTTP
        - ``web.*``          — web search
        - ``git.*``          — git VCS operations
        - ``env.*``          — environment variables
        - ``notebook.*``     — Jupyter notebook editing
        - ``interaction.*``  — human-in-the-loop prompts
        - ``agent.*``        — sub-agent delegation
        - ``todo.*``         — todo list management
        - ``agentbox.*``     — agentbox-internal capabilities
    """

    # ── Filesystem ───────────────────────────────────────────────────────────
    FS_READ = "fs.read"
    FS_WRITE = "fs.write"
    FS_EDIT = "fs.edit"
    FS_MULTI_EDIT = "fs.multi_edit"
    FS_LIST = "fs.list"
    FS_GLOB = "fs.glob"
    FS_GREP = "fs.grep"

    # ── Shell ────────────────────────────────────────────────────────────────
    SHELL_EXEC = "shell.exec"

    # ── HTTP / Web ───────────────────────────────────────────────────────────
    HTTP_FETCH = "http.fetch"
    WEB_SEARCH = "web.search"

    # ── Git ──────────────────────────────────────────────────────────────────
    GIT_STATUS = "git.status"
    GIT_LOG = "git.log"
    GIT_DIFF = "git.diff"

    # ── Environment ──────────────────────────────────────────────────────────
    ENV_GET = "env.get"

    # ── Notebook ─────────────────────────────────────────────────────────────
    NOTEBOOK_EDIT = "notebook.edit"

    # ── Interaction ──────────────────────────────────────────────────────────
    INTERACTION_ASK_USER = "interaction.ask_user"

    # ── Agent / Task ─────────────────────────────────────────────────────────
    AGENT_TASK = "agent.task"

    # ── Todo ─────────────────────────────────────────────────────────────────
    TODO_READ = "todo.read"
    TODO_WRITE = "todo.write"

    # ── Agentbox ─────────────────────────────────────────────────────────────
    AGENTBOX_WORKSPACE_INFO = "agentbox.workspace_info"


__all__ = ["CanonicalTool"]
