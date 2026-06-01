"""Spawn the environment_mcp stdio server.

Invoked by the executor's mcp_inject via
``python -m agentbox.core.tools.environment_mcp``.
"""

from agentbox.core.tools.environment_mcp.server import build_server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
