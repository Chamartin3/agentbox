"""Serve command — run the FastAPI server."""

from __future__ import annotations

import uvicorn


def serve(host: str = "0.0.0.0", port: int = 8765) -> None:
    """Run the FastAPI server."""
    uvicorn.run("agentbox.api.app:app", host=host, port=port, log_level="info")
