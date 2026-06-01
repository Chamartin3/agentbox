"""Credential state enumeration."""

from __future__ import annotations

from enum import Enum


class CredentialState(str, Enum):
    MISSING = "missing"
    PRESENT = "present"
    INVALID = "invalid"
