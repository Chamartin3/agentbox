"""Cross-cutting services that compose ``core/data`` + ``core/definitions``.

Use these from both the REST API and the MCP server so the two surfaces
always answer with the same data. Routes/tools should not re-implement
DB-vs-loader fallback logic.
"""
