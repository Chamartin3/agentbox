"""Hashing helpers for shared resources."""

import hashlib
import json


def _compute_sha256(content: str | None, config_json: str | None) -> str:
    """Compute canonical sha256 from content or config_json."""
    if content is not None:
        canonical = content
    elif config_json is not None:
        obj = json.loads(config_json)
        canonical = json.dumps(obj, sort_keys=True)
    else:
        canonical = ""
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
