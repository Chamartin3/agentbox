"""Workspace-scoped data layer.

Submodules:
- crud: WorkspacesMixin — canonical workspace registry CRUD + cascade delete
- env_docs: EnvDocsMixin — per-workspace env doc versioning
- mcp_overrides: McpOverridesMixin — workspace MCP server/tool enable/disable + policy
- mcp_discovery: McpDiscoveryMixin — MCP tool discovery cache with TTL
- runtime_permissions: RuntimePermissionsMixin — workspace runtime permissions overlay
- host_env: HostEnvMixin — host-env profile CRUD + workspace grant + audit log
"""
