"""Shared fixtures for the MCP client tests.

The discovery suites previously each carried an identical ``_run`` event-loop
helper. It lives here now as a single fixture consumed via DI.
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def run_coro():
    """Run a coroutine in a fresh, guaranteed-closed event loop.

    Use a dedicated loop (created + closed inside the helper) instead of
    ``asyncio.get_event_loop()`` so the loop is closed before the test
    exits — otherwise pytest's unraisable collection surfaces
    ResourceWarnings from leftover loops in later tests.
    """

    def _run(coro):  # type: ignore[no-untyped-def]
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    return _run
