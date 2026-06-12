"""Observability facade — capture, stream, and decode run artifacts.

Three timeline positions, one importable namespace:

* ``snapshot`` — prep-time capture of runner/MCP/resource snapshots.
* ``stream`` — live event emission (transcript + WebSocket + accumulators).
* ``conversation`` — post-run decoding of runner-native conversation logs.
"""

from __future__ import annotations

# captures (prep-time)
from .snapshot import (
    SnapshotWriter,
    build_mcp_snapshot,
    build_resource_snapshot_entries,
    build_runner_snapshot,
)

# emission (live)
from .stream import CaptureSession, RunStreamSession

# decoding (post)
from .conversation import (
    ConversationSource,
    ConversationView,
    Turn,
    available_formats,
    get,
)

# Backward-compatible aliases for the names used in the observability
# module spec (ConversationTurn/ConversationHistory were renamed to
# Turn/ConversationView in the underlying conversation package).
ConversationTurn = Turn
ConversationHistory = ConversationView
get_conversation_source = get
list_conversation_sources = available_formats

__all__ = [
    # snapshot
    "SnapshotWriter",
    "build_mcp_snapshot",
    "build_resource_snapshot_entries",
    "build_runner_snapshot",
    # stream
    "CaptureSession",
    "RunStreamSession",
    # conversation
    "ConversationHistory",
    "ConversationSource",
    "ConversationTurn",
    "ConversationView",
    "Turn",
    "available_formats",
    "get",
    "get_conversation_source",
    "list_conversation_sources",
]
