"""Host-environment FastMCP server (Plan 08 Phase 3).

Run as a stdio subprocess via the executor:
    python -m agentbox.core.workspace.mcp.servers.host_env

Env vars injected by the executor:
    AGENTBOX_HOST_ENV_GRANTS_JSON  — JSON dict of effective grants
    AGENTBOX_HOST_ENV_RUN_ID       — run_id for audit logging
    AGENTBOX_HOST_ENV_WORKSPACE_ID — workspace_id for audit logging
    AGENTBOX_HOST_ENV_WORKDIR      — workdir path (workspace_info tool)
    AGENTBOX_DB_PATH               — path to the SQLite store (audit log)
"""
