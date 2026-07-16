"""SystemService — settings, API tokens, project config, host-env call log.

Consolidates the system domain: every operation that used to live on the
``SessionStore`` mixins (SettingsMixin, ProjectConfigMixin, ApiTokensMixin,
HostEnvCallLogMixin) and the free functions in ``system_admin.py``.

Extends ``Service`` (self-wiring ``Database`` from settings). Callers
construct with no arguments: ``SystemService()``.

Token secret generation, Fernet encryption, JSON encoding/decoding, and
timestamp stamps all live here as service policy — managers only do
pure DB reads and writes.
"""
from __future__ import annotations

import base64
import hashlib
import json as _json
import secrets as _secrets
import uuid

from cryptography.fernet import Fernet, InvalidToken

from pathlib import Path

from agentbox.core.config import SETTINGS, load_settings
from agentbox.core.data import DoctorCheck, McpServerSpec, now_iso
from agentbox.core.data.rows import (
    ApiTokenPublicRow,
    ApiTokenRow,
    ApiTokenWithSecret,
    HostEnvCallLogRow,
)
from agentbox.core.service.base import Service


class SystemService(Service):
    """Public API for the system/config domain.

    Settings, project MCP servers, shared assets, API tokens, and host-env
    call log all live here. Construction is zero-argument — ``Database``
    is resolved internally from settings.
    """

    def __init__(self) -> None:
        super().__init__()

    # ══════════════════════════════════════════════════════════════════
    # Settings
    # ══════════════════════════════════════════════════════════════════

    def get_settings_section(self, section: str) -> dict:
        """Return all ``{key: value}`` pairs in a section (deserialised)."""
        return self._db.settings.get_settings_section(section)

    def get_setting(
        self, section: str, key: str, default: object = None
    ) -> object:
        """Return one setting value, or *default* if not present."""
        raw = self._db.settings.get_value(section, key)
        if raw is None:
            return default
        try:
            return _json.loads(raw)
        except (_json.JSONDecodeError, TypeError):
            return raw

    def set_setting(
        self,
        section: str,
        key: str,
        value: object,
        *,
        author: str | None = None,
    ) -> None:
        """Upsert a single setting."""
        ts = now_iso()
        payload = _json.dumps(value)
        self._db.settings.upsert(section, key, payload, ts, author)

    def update_settings_section(
        self,
        section: str,
        patch: dict,
        *,
        author: str | None = None,
    ) -> dict:
        """Apply a partial patch to a section. Returns the full section."""
        for key, value in patch.items():
            self.set_setting(section, key, value, author=author)
        return self.get_settings_section(section)

    def list_settings_sections(self) -> list[str]:
        """Return distinct section names that have at least one key set."""
        return self._db.settings.list_sections()

    # ══════════════════════════════════════════════════════════════════
    # Project MCP servers
    # ══════════════════════════════════════════════════════════════════

    PROJ_MCP_SERVERS = "project_mcp_servers"

    def get_project_mcp_servers(self) -> list[McpServerSpec]:
        """List project-level MCP servers (deserialised from settings)."""
        section = self.get_settings_section(self.PROJ_MCP_SERVERS)
        out: list[McpServerSpec] = []
        for name, raw in section.items():
            if not isinstance(raw, dict):
                continue
            data = {**raw, "name": raw.get("name") or name}
            try:
                out.append(McpServerSpec.model_validate(data))
            except Exception:
                continue
        return out

    def set_project_mcp_server(
        self,
        spec: McpServerSpec,
        *,
        author: str | None = None,
    ) -> None:
        """Upsert a project-level MCP server spec."""
        self.set_setting(
            self.PROJ_MCP_SERVERS,
            spec.name,
            spec.model_dump(mode="json"),
            author=author,
        )

    def delete_project_mcp_server(self, name: str) -> None:
        """Delete a project-level MCP server by name."""
        self._db.settings.delete_section_key(self.PROJ_MCP_SERVERS, name)

    # ══════════════════════════════════════════════════════════════════
    # Project shared assets
    # ══════════════════════════════════════════════════════════════════

    PROJ_SHARED_ASSETS = "project_shared_assets"

    def get_project_shared_assets(self) -> dict[str, str]:
        """Return the project shared-asset roots as ``{name: path}``."""
        section = self.get_settings_section(self.PROJ_SHARED_ASSETS)
        return {k: str(v) for k, v in section.items() if isinstance(v, str)}

    def get_project_shared_roots(self) -> dict[str, Path]:
        """Return shared-asset paths resolved against the project root.

        Combines ``get_project_shared_assets()`` with ``SETTINGS.project_root``
        so callers need only ``ctx.system`` — no direct settings access.
        """
        project_root = SETTINGS.project_root
        return {key: project_root / rel for key, rel in self.get_project_shared_assets().items()}

    def set_project_shared_asset(
        self, name: str, path: str, *, author: str | None = None
    ) -> None:
        """Upsert a shared asset root path."""
        self.set_setting(self.PROJ_SHARED_ASSETS, name, path, author=author)

    def delete_project_shared_asset(self, name: str) -> None:
        """Delete a shared asset root entry."""
        self._db.settings.delete_section_key(self.PROJ_SHARED_ASSETS, name)

    # ══════════════════════════════════════════════════════════════════
    # Project runtime scalars
    # ══════════════════════════════════════════════════════════════════

    PROJ_RUNTIME = "project_runtime"

    def get_backend_preference(self) -> list[str]:
        """Return the ordered backend preference list."""
        value = self.get_setting(self.PROJ_RUNTIME, "backend_preference", default=[])
        if isinstance(value, list):
            return [str(v) for v in value]
        return []

    def set_backend_preference(
        self, names: list[str], *, author: str | None = None
    ) -> None:
        """Store the ordered backend preference list."""
        self.set_setting(
            self.PROJ_RUNTIME, "backend_preference", list(names), author=author
        )

    def get_tool_manifest_path(self) -> str | None:
        """Return the project tool manifest path, or None."""
        value = self.get_setting(self.PROJ_RUNTIME, "tool_manifest_path", default=None)
        return str(value) if value else None

    def get_project_name(self) -> str:
        """Return the project name (defaults to ``"default"``)."""
        value = self.get_setting(self.PROJ_RUNTIME, "project_name", default="default")
        return str(value) if value else "default"

    # ══════════════════════════════════════════════════════════════════
    # API tokens
    # ══════════════════════════════════════════════════════════════════

    def list_api_tokens(
        self, *, environment: str | None = None
    ) -> list[ApiTokenRow]:
        """List API tokens, optionally filtered by environment."""
        return self._db.api_tokens.list_tokens(environment=environment)

    def create_api_token(
        self,
        name: str,
        *,
        environment: str = "production",
        secret: str | None = None,
    ) -> ApiTokenPublicRow:
        """Create a new API token. The plaintext secret is returned only here.

        When *secret* is not provided, a 256-bit URL-safe secret is generated.
        """
        if secret is None:
            secret = _secrets.token_urlsafe(32)
        if len(secret) < 4:
            raise ValueError("secret must be at least 4 characters")
        token_id = uuid.uuid4().hex
        ts = now_iso()
        encrypted = self._fernet().encrypt(secret.encode()).decode()
        last_four = secret[-4:]
        return self._db.api_tokens.insert_token(
            token_id=token_id,
            environment=environment,
            name=name,
            secret_encrypted=encrypted,
            last_four=last_four,
            created_at=ts,
            updated_at=ts,
        )

    def rename_api_token(self, token_id: str, name: str) -> ApiTokenRow | None:
        """Rename an API token. Returns the updated row or None."""
        ts = now_iso()
        return self._db.api_tokens.update_token_name(token_id, name, ts)

    def rotate_api_token(
        self, token_id: str, *, secret: str | None = None
    ) -> ApiTokenWithSecret | None:
        """Rotate a token's secret. Returns the updated row (with plaintext secret) or None."""
        if secret is None:
            secret = _secrets.token_urlsafe(32)
        if len(secret) < 4:
            raise ValueError("secret must be at least 4 characters")
        ts = now_iso()
        encrypted = self._fernet().encrypt(secret.encode()).decode()
        last_four = secret[-4:]
        result = self._db.api_tokens.update_token_secret(
            token_id, encrypted, last_four, ts
        )
        if result is not None:
            return {**result, "secret": secret}
        return None

    def delete_api_token(self, token_id: str) -> bool:
        """Delete an API token. Returns True if a row was deleted."""
        return self._db.api_tokens.delete_token(token_id)

    def reveal_api_token(self, token_id: str) -> str | None:
        """Decrypt and return the plaintext secret. Use with extreme care."""
        raw = self._db.api_tokens.get_token_secret_encrypted(token_id)
        if raw is None:
            return None
        try:
            return self._fernet().decrypt(raw.encode()).decode()
        except InvalidToken:
            return None

    def _fernet(self) -> Fernet:
        """Return a Fernet instance keyed from env or per-DB persisted key."""
        return Fernet(_fernet_key(self))

    # ══════════════════════════════════════════════════════════════════
    # Host-env call log
    # ══════════════════════════════════════════════════════════════════

    def record_host_env_call(
        self,
        *,
        run_id: str,
        workspace_id: str,
        capability: str,
        params: dict | None,
        status: str,
        error: str | None = None,
        surface: str = "host_env",
    ) -> str:
        """Insert an audit log row for a host-env call. Returns the row id."""
        row_id = uuid.uuid4().hex
        self._db.host_env_call_log.insert_call(
            row_id=row_id,
            run_id=run_id,
            workspace_id=workspace_id,
            capability=capability,
            params=params,
            status=status,
            error=error,
            surface=surface,
            created_at=now_iso(),
        )
        return row_id

    def list_host_env_calls_for_run(self, run_id: str) -> list[HostEnvCallLogRow]:
        """List all host-env call log entries for a run."""
        return self._db.host_env_call_log.list_calls_for_run(run_id)

    # ══════════════════════════════════════════════════════════════════
    # Diagnostics
    # ══════════════════════════════════════════════════════════════════

    def doctor_checks(self) -> list[DoctorCheck]:
        """Run the diagnostic suite and return one result per check.

        The interface layer renders and decides the exit code; this method
        owns the checks. Sibling services self-wire from settings, so this
        aggregator constructs them locally.
        """
        # Local imports: sibling services + workspace helper, avoiding a
        # module-level cycle through the service facade.
        from agentbox.core.service.agents import AgentService  # noqa: PLC0415
        from agentbox.core.service.engines import (  # noqa: PLC0415
            CredentialState,
            EngineService,
        )
        from agentbox.core.service.execution import ExecutionService  # noqa: PLC0415
        from agentbox.core.workspaces.workdir import info as workspace_info  # noqa: PLC0415

        settings = load_settings()
        checks: list[DoctorCheck] = []

        def ok(name: str, detail: str = "") -> None:
            checks.append(DoctorCheck(name, True, detail))

        def fail(name: str, detail: str) -> None:
            checks.append(DoctorCheck(name, False, detail))

        try:
            rows = [workspace_info(a, settings) for a in AgentService().list_all_agents()]
            resolvable = True
            for w in rows:
                if not w.exists and not w.ephemeral:
                    resolvable = False
                    ok("Workspaces", f"{w.agent_id}: path {w.path} does not exist")
            if resolvable:
                ok("Workspaces", f"{len(rows)} agent(s), all paths resolvable")
        except Exception as exc:
            fail("Workspaces", str(exc))

        try:
            ExecutionService().list_runs(limit=1)
            ok("Database", str(settings.db_path))
        except Exception as exc:
            fail("Database", str(exc))

        engines = EngineService()
        try:
            ok("Plugins", f"{len(engines.list_backend_names())} backend(s)")
        except Exception as exc:
            fail("Plugins", str(exc))

        try:
            creds = engines.list_credentials()
            if not creds:
                ok("Credentials", "no backends registered")
            else:
                ok("Credentials", f"{len(creds)} backend(s)")
                for r in creds:
                    label = "configured" if r.detect() == CredentialState.PRESENT else "missing"
                    ok(f"  {r.backend}", label)
        except Exception as exc:
            ok("Credentials", str(exc))

        cache = settings.mcp_cache_dir
        if cache.exists():
            ok("MCP cache", f"{len(list(cache.glob('*.json')))} cached server(s) in {cache}")
        else:
            ok("MCP cache", f"cache dir {cache} does not exist")

        return checks


# ------------------------------------------------------------------
# Fernet key derivation (module-level, extracted from ApiTokensMixin)
# ------------------------------------------------------------------


def _fernet_key(service: SystemService) -> bytes:
    """Return a Fernet key. Prefers ``AGENTBOX_SECRET_KEY``; falls back to
    a per-DB key persisted under settings(secrets, fernet_key).
    """
    env_val = SETTINGS.secret_key
    if env_val:
        try:
            Fernet(env_val.encode())
            return env_val.encode()
        except (ValueError, Exception):
            digest = hashlib.sha256(env_val.encode()).digest()
            return base64.urlsafe_b64encode(digest)

    existing = service.get_setting("secrets", "fernet_key")
    if existing:
        if isinstance(existing, bytes):
            return existing
        if isinstance(existing, str):
            return existing.encode()
    # No valid key stored → generate
    new_key = Fernet.generate_key()
    service.set_setting("secrets", "fernet_key", new_key.decode(), author="system")
    return new_key
