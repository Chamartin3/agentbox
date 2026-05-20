"""Validation contracts mixin.

Two tables, one mixin:

- ``validation_contracts`` — reusable {name, rules[], validator?} entity.
- ``agent_version_validation_bindings`` — per (agent_version_id, direction)
  pointer at a contract.

Schema validation stays in ``agent_prompt_resource_bindings`` (slot=
``input_schema``/``output_schema``). Rules + validator live here so they
can be shared across agents and edited independently of the schema.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable

from sqlalchemy import and_, select
from sqlalchemy.engine import Engine

from agentbox.core.data.records import now_iso
from agentbox.core.data.schema import (
    agent_version_validation_bindings,
    validation_contracts,
)

VALID_DIRECTIONS = ("input", "output")


def _decode_rules(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return [r for r in parsed if isinstance(r, str)] if isinstance(parsed, list) else []


def _decode_validators(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [v for v in parsed if isinstance(v, dict)]


def _row_to_contract(row) -> dict:
    d = dict(row._mapping)
    d["rules"] = _decode_rules(d.get("rules"))
    d["validators"] = _decode_validators(d.get("validators"))
    return d


def _validate_rules(rules: Iterable[str] | None) -> list[str]:
    if rules is None:
        return []
    out: list[str] = []
    for r in rules:
        if not isinstance(r, str):
            raise ValueError("rules must be a list of strings")
        out.append(r)
    return out


# Known validator kinds. The jsonschema validator is implicit from the
# agent's `output_schema` binding — never listed here. Adding a new
# kind requires:
#   1. Adding it here + a normaliser branch in _validate_single_validator
#   2. Adding a runtime dispatch branch in core/run/validation.validate_output
#   3. (If resource-backed) adding a resolver branch in
#      core/agent/config.resolve_output_config that pre-loads the blob.
VALID_VALIDATOR_KINDS = ("http", "script")


def _validate_single_validator(val: dict) -> dict:
    if not isinstance(val, dict):
        raise ValueError("validator entry must be an object")
    kind = val.get("kind", "http")
    if kind not in VALID_VALIDATOR_KINDS:
        raise ValueError(
            f"unknown validator kind {kind!r}; must be one of "
            f"{VALID_VALIDATOR_KINDS}. The jsonschema validator is implicit "
            "from the agent's output_schema binding and must not be listed "
            "here."
        )
    desc_raw = val.get("description", "")
    if desc_raw is None:
        desc_raw = ""
    if not isinstance(desc_raw, str):
        raise ValueError("validator.description must be a string")
    if kind == "http":
        endpoint = val.get("endpoint")
        if not isinstance(endpoint, str) or not endpoint:
            raise ValueError("http validator requires a non-empty endpoint")
        out: dict = {
            "kind": "http",
            "endpoint": endpoint,
            "timeout_seconds": int(val.get("timeout_seconds", 5)),
        }
        if desc_raw:
            out["description"] = desc_raw
        return out
    if kind == "script":
        resource_id = val.get("resource_id")
        if not isinstance(resource_id, str) or not resource_id:
            raise ValueError(
                "script validator requires resource_id (pointing at a "
                "repo_resource of type='script')"
            )
        pinned = val.get("pinned_version_id")
        if pinned is not None and not isinstance(pinned, str):
            raise ValueError("script.pinned_version_id must be a string or null")
        out = {"kind": "script", "resource_id": resource_id}
        if pinned:
            out["pinned_version_id"] = pinned
        if desc_raw:
            out["description"] = desc_raw
        return out
    # Unreachable given the kind check above, but keep the branch
    # explicit so future kinds force their normaliser to be added.
    raise ValueError(f"validator kind {kind!r} has no normaliser")


def _validate_validators(validators: Iterable[dict] | None) -> list[dict]:
    if validators is None:
        return []
    return [_validate_single_validator(v) for v in validators]


class ValidationContractsMixin:
    """CRUD for validation contracts + per-(version, direction) bindings."""

    engine: Engine

    # --- contracts ---

    def create_validation_contract(
        self,
        *,
        name: str,
        rules: Iterable[str] | None = None,
        validators: Iterable[dict] | None = None,
        description: str | None = None,
        actor: str | None = None,
    ) -> dict:
        if not name or not name.strip():
            raise ValueError("name is required")
        rules_list = _validate_rules(rules)
        vals = _validate_validators(validators)
        cid = uuid.uuid4().hex
        now = now_iso()
        with self.engine.begin() as conn:
            conn.execute(
                validation_contracts.insert().values(
                    id=cid,
                    name=name.strip(),
                    description=description,
                    rules=json.dumps(rules_list),
                    validators=json.dumps(vals),
                    created_at=now,
                    updated_at=now,
                    created_by=actor,
                )
            )
        return self.get_validation_contract(cid) or {}

    def update_validation_contract(
        self,
        contract_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        rules: Iterable[str] | None = None,
        validators: Iterable[dict] | None = None,
    ) -> dict:
        existing = self.get_validation_contract(contract_id)
        if not existing:
            raise ValueError(f"validation_contract {contract_id!r} not found")
        patch: dict = {"updated_at": now_iso()}
        if name is not None:
            if not name.strip():
                raise ValueError("name cannot be empty")
            patch["name"] = name.strip()
        if description is not None:
            patch["description"] = description
        if rules is not None:
            patch["rules"] = json.dumps(_validate_rules(rules))
        if validators is not None:
            patch["validators"] = json.dumps(_validate_validators(validators))
        with self.engine.begin() as conn:
            conn.execute(
                validation_contracts.update()
                .where(validation_contracts.c.id == contract_id)
                .values(**patch)
            )
        return self.get_validation_contract(contract_id) or {}

    def delete_validation_contract(self, contract_id: str) -> None:
        # FK is RESTRICT — surfaces a clear error if still referenced.
        with self.engine.begin() as conn:
            conn.execute(
                validation_contracts.delete().where(
                    validation_contracts.c.id == contract_id
                )
            )

    def get_validation_contract(self, contract_id: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                validation_contracts.select().where(
                    validation_contracts.c.id == contract_id
                )
            ).first()
        return _row_to_contract(row) if row else None

    def get_validation_contract_by_name(self, name: str) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                validation_contracts.select().where(
                    validation_contracts.c.name == name
                )
            ).first()
        return _row_to_contract(row) if row else None

    def list_validation_contracts(
        self,
        *,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        stmt = validation_contracts.select()
        if query:
            like = f"%{query}%"
            stmt = stmt.where(validation_contracts.c.name.ilike(like))
        stmt = (
            stmt.order_by(validation_contracts.c.name).limit(limit).offset(offset)
        )
        with self.engine.connect() as conn:
            return [_row_to_contract(r) for r in conn.execute(stmt)]

    def count_contract_references(self, contract_id: str) -> int:
        from sqlalchemy import func

        with self.engine.connect() as conn:
            n = conn.execute(
                select(func.count()).select_from(
                    agent_version_validation_bindings
                ).where(
                    agent_version_validation_bindings.c.contract_id == contract_id
                )
            ).scalar()
        return int(n or 0)

    # --- per (agent_version, direction) bindings ---

    def set_agent_version_validation(
        self,
        agent_version_id: int,
        *,
        direction: str,
        contract_id: str | None,
        actor: str | None = None,
    ) -> None:
        if direction not in VALID_DIRECTIONS:
            raise ValueError(
                f"direction must be one of {VALID_DIRECTIONS}, got {direction!r}"
            )
        with self.engine.begin() as conn:
            conn.execute(
                agent_version_validation_bindings.delete().where(
                    and_(
                        agent_version_validation_bindings.c.agent_version_id
                        == agent_version_id,
                        agent_version_validation_bindings.c.direction == direction,
                    )
                )
            )
            if contract_id is not None:
                conn.execute(
                    agent_version_validation_bindings.insert().values(
                        agent_version_id=agent_version_id,
                        direction=direction,
                        contract_id=contract_id,
                        created_at=now_iso(),
                        created_by=actor,
                    )
                )

    def list_agent_version_validations(
        self, agent_version_id: int
    ) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                agent_version_validation_bindings.select().where(
                    agent_version_validation_bindings.c.agent_version_id
                    == agent_version_id
                )
            )
            return [dict(r._mapping) for r in rows]

    def get_agent_version_validation(
        self, agent_version_id: int, direction: str
    ) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                agent_version_validation_bindings.select().where(
                    and_(
                        agent_version_validation_bindings.c.agent_version_id
                        == agent_version_id,
                        agent_version_validation_bindings.c.direction == direction,
                    )
                )
            ).first()
        return dict(row._mapping) if row else None

    def resolve_agent_version_contract(
        self, agent_version_id: int, direction: str
    ) -> dict | None:
        """Return the bound contract (full row, rules/validator decoded)
        for a given (version, direction) — or None if no binding."""
        binding = self.get_agent_version_validation(agent_version_id, direction)
        if not binding:
            return None
        return self.get_validation_contract(binding["contract_id"])

    def clone_validation_bindings(
        self, *, from_version_id: int, to_version_id: int
    ) -> None:
        """Copy every (direction, contract_id) row from one version to another.

        Used by ``create_version`` to carry validation forward when a new
        agent_version is created (prompt edits, runner edits, etc.) so the
        contract follows the agent unless explicitly changed.
        """
        if from_version_id == to_version_id:
            return
        with self.engine.begin() as conn:
            src = conn.execute(
                agent_version_validation_bindings.select().where(
                    agent_version_validation_bindings.c.agent_version_id
                    == from_version_id
                )
            ).all()
            if not src:
                return
            now = now_iso()
            conn.execute(
                agent_version_validation_bindings.insert(),
                [
                    {
                        "agent_version_id": to_version_id,
                        "direction": r._mapping["direction"],
                        "contract_id": r._mapping["contract_id"],
                        "created_at": now,
                        "created_by": r._mapping.get("created_by"),
                    }
                    for r in src
                ],
            )
