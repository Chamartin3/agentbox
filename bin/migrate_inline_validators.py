"""Plan 23 Phase 2 — fan validation-contract bindings into inline
``config_json[direction].validators`` on each bound agent version.

Idempotent. For every row in ``agent_version_validation_bindings``:

1. Load the bound contract's validators.
2. Open the target ``agent_versions.config_json``.
3. If that direction already has inline validators, skip — the version
   has already been migrated (or was authored inline directly).
4. Otherwise write ``validators`` under ``config_json[direction]`` and
   delete the binding row.

Run inside the container:

    docker compose exec agentbox python -m bin.migrate_inline_validators

Or against a custom DB:

    AGENTBOX_DB_URL=... uv run python -m bin.migrate_inline_validators
"""

from __future__ import annotations

import json
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from agentbox.core.data.schema import (
    agent_version_validation_bindings,
    agent_versions,
    validation_contracts,
)


def _resolve_db_url() -> str:
    url = os.environ.get("AGENTBOX_DB_URL")
    if url:
        return url
    # Fall back to the same SQLite path the app uses so the script works
    # inside the cvagents-agentbox container with no env tweaks.
    from agentbox.config import SETTINGS

    return f"sqlite:///{SETTINGS.db_path}"


def _decode(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _has_inline_validators(cfg: dict, direction: str) -> bool:
    section = cfg.get(direction)
    if not isinstance(section, dict):
        return False
    inline = section.get("validators")
    return isinstance(inline, list) and bool(inline)


def migrate(engine: Engine) -> tuple[int, int]:
    """Walk every binding row. Returns (migrated, skipped)."""
    migrated = 0
    skipped = 0

    with engine.begin() as conn:
        bindings = conn.execute(
            agent_version_validation_bindings.select()
        ).all()
        print(f"[plan-23] {len(bindings)} binding rows to evaluate", flush=True)

        for b in bindings:
            mapping = b._mapping
            version_id = int(mapping["agent_version_id"])
            direction = str(mapping["direction"])
            contract_id = str(mapping["contract_id"])

            contract_row = conn.execute(
                validation_contracts.select().where(
                    validation_contracts.c.id == contract_id
                )
            ).first()
            if contract_row is None:
                print(
                    f"  ! version={version_id} dir={direction}: contract "
                    f"{contract_id!r} missing — dropping binding",
                    flush=True,
                )
                conn.execute(
                    agent_version_validation_bindings.delete().where(
                        (
                            agent_version_validation_bindings.c.agent_version_id
                            == version_id
                        )
                        & (
                            agent_version_validation_bindings.c.direction
                            == direction
                        )
                    )
                )
                skipped += 1
                continue

            validators_raw = contract_row._mapping.get("validators")
            try:
                validators = json.loads(validators_raw or "[]")
            except (ValueError, TypeError):
                validators = []
            if not isinstance(validators, list):
                validators = []

            version_row = conn.execute(
                agent_versions.select().where(agent_versions.c.id == version_id)
            ).first()
            if version_row is None:
                print(
                    f"  ! version={version_id}: agent_versions row missing "
                    f"— dropping binding",
                    flush=True,
                )
                conn.execute(
                    agent_version_validation_bindings.delete().where(
                        (
                            agent_version_validation_bindings.c.agent_version_id
                            == version_id
                        )
                        & (
                            agent_version_validation_bindings.c.direction
                            == direction
                        )
                    )
                )
                skipped += 1
                continue

            cfg = _decode(version_row._mapping.get("config_json"))
            if _has_inline_validators(cfg, direction):
                print(
                    f"  = version={version_id} dir={direction}: already inline, "
                    f"dropping binding only",
                    flush=True,
                )
                conn.execute(
                    agent_version_validation_bindings.delete().where(
                        (
                            agent_version_validation_bindings.c.agent_version_id
                            == version_id
                        )
                        & (
                            agent_version_validation_bindings.c.direction
                            == direction
                        )
                    )
                )
                skipped += 1
                continue

            section = cfg.get(direction)
            if not isinstance(section, dict):
                section = {}
            section["validators"] = validators
            cfg[direction] = section

            conn.execute(
                agent_versions.update()
                .where(agent_versions.c.id == version_id)
                .values(config_json=json.dumps(cfg))
            )
            conn.execute(
                agent_version_validation_bindings.delete().where(
                    (
                        agent_version_validation_bindings.c.agent_version_id
                        == version_id
                    )
                    & (
                        agent_version_validation_bindings.c.direction
                        == direction
                    )
                )
            )
            print(
                f"  + version={version_id} dir={direction}: inlined "
                f"{len(validators)} validator(s) from {contract_id}",
                flush=True,
            )
            migrated += 1

    return migrated, skipped


def main() -> int:
    url = _resolve_db_url()
    print(f"[plan-23] connecting to {url}", flush=True)
    engine = create_engine(url)
    migrated, skipped = migrate(engine)

    with engine.connect() as conn:
        remaining = conn.execute(
            agent_version_validation_bindings.select()
        ).all()
    print(
        f"[plan-23] done. migrated={migrated} skipped={skipped} "
        f"remaining_bindings={len(remaining)}",
        flush=True,
    )
    return 0 if not remaining else 1


if __name__ == "__main__":
    sys.exit(main())
