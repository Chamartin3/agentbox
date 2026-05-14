#!/bin/bash
# Wrapper for agentbox-mcp to ensure env vars are set
export AGENTBOX_MCP_TRANSPORT=stdio
export AGENTBOX_DATA_DIR=/home/omidev/Code/ai/cv_agents/workdir/agentbox/data
export AGENTBOX_PROJECT_ROOT=/home/omidev/Code/ai/cv_agents
export AGENTBOX_MANIFEST=/home/omidev/Code/ai/cv_agents/agentbox.toml
export AGENTBOX_AGENTS_BUNDLE_DIR=/home/omidev/Code/ai/cv_agents/apps/cvman/ai/agents
exec uv --directory /home/omidev/Code/ai/cv_agents/libs/agentbox run agentbox-mcp
