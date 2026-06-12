"""Concrete dispatch channels."""

from __future__ import annotations

from .base import DispatchChannel
from .types import DeliveryResult
from .webhook import WebhookChannel

__all__ = ["DeliveryResult", "DispatchChannel", "WebhookChannel"]
