"""Run credential-env construction, shared across backend adapters.

One rule, applied by every backend so the behavior is uniform:

- ``creds is None`` → the workspace has **not** configured credentials.
  Inherit the full process env (legacy behavior; nothing breaks on upgrade).
- ``creds`` is a dict → the workspace **opted in** to per-workspace
  credentials. Scrub every provider key from the base env and inject only
  the credentials the workspace enabled. This is the least-privilege path:
  an agent sees exactly the keys its workspace granted, not the whole
  container env.

ponytail: an empty configured set can't currently mean "grant nothing" —
empty is treated as "unconfigured → inherit". Revisit if a workspace ever
needs a hard zero-credential guarantee.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from agentbox.core.data.constants import PROVIDER_KEY_ENV_VARS


def build_run_env(
    creds: Mapping[str, str] | None,
    *,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Base env for a run's agent subprocess (see module docstring).

    *extra* is merged after ``os.environ`` (provider-key stripped) but
    before *creds* — so workspace custom env vars are visible, but
    credential-managed provider keys always win over same-named vars.
    """
    if creds is None and extra is None:
        return dict(os.environ)
    env = {k: v for k, v in os.environ.items() if k not in PROVIDER_KEY_ENV_VARS}
    if extra:
        env.update(extra)
    if creds:
        env.update(creds)
    return env
