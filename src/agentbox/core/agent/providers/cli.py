"""CLI-backed provider adapters for local tool model catalogs."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
from typing import Any

from agentbox.core.agent.providers.base import (
    Provider,
    ProviderDescriptor,
    ProviderModel,
)

logger = logging.getLogger(__name__)


async def _run_cli(command: list[str], timeout_s: float = 10.0) -> str:
    if not command or shutil.which(command[0]) is None:
        return ""

    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        logger.warning("%s timed out while listing models", command[0])
        return ""

    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        logger.warning("%s model listing failed: %s", command[0], err)
        return ""
    return stdout.decode(errors="replace")


def _run_cli_sync(command: list[str], timeout_s: float = 10.0) -> str:
    if not command or shutil.which(command[0]) is None:
        return ""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("%s timed out while listing models", command[0])
        return ""
    if result.returncode != 0:
        err = result.stderr.decode(errors="replace").strip()
        logger.warning("%s model listing failed: %s", command[0], err)
        return ""
    return result.stdout.decode(errors="replace")


def discover_opencode_providers() -> list[str]:
    """Run ``opencode models`` and return the sorted set of provider prefixes.

    ``opencode`` filters its output by configured credentials — so the set
    grows automatically as more API keys / auth tokens become available
    inside the container. Returns an empty list when the binary is
    missing or the call fails.
    """
    output = _run_cli_sync(["opencode", "models"], timeout_s=10.0)
    if not output:
        return []
    prefixes: set[str] = set()
    for line in output.splitlines():
        line = line.strip().strip("`\"'")
        if not line or "/" not in line:
            continue
        prefix = line.split("/", 1)[0]
        if prefix:
            prefixes.add(prefix)
    return sorted(prefixes)


def _compact_codex_raw(item: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "slug",
        "display_name",
        "description",
        "visibility",
        "supported_in_api",
        "priority",
    )
    return {key: item[key] for key in keep if key in item}


class CodexCLIAdapter:
    descriptor = ProviderDescriptor(
        id=Provider.CODEX.value,
        label="Codex CLI",
        backend="codex",
        compatible_backends=["codex"],
        requires_api_key=False,
        supports_base_url=False,
        supports_model_listing=True,
    )

    async def list_models(self, config: Any) -> list[ProviderModel]:
        output = await _run_cli(["codex", "debug", "models"], timeout_s=10.0)
        if not output:
            return []
        try:
            data = json.loads(output)
        except json.JSONDecodeError as exc:
            logger.warning("codex model catalog was not valid JSON: %s", exc)
            return []

        models: list[ProviderModel] = []
        for item in data.get("models", []):
            if not isinstance(item, dict):
                continue
            slug = item.get("slug")
            if not isinstance(slug, str) or not slug:
                continue
            models.append(
                ProviderModel(
                    id=slug,
                    name=item.get("display_name") or slug,
                    raw=_compact_codex_raw(item),
                )
            )
        return models


def _parse_opencode_lines(output: str, provider_id: str) -> list[ProviderModel]:
    seen: set[str] = set()
    models: list[ProviderModel] = []
    prefix = f"{provider_id}/"
    for line in output.splitlines():
        model_id = line.strip().strip("`\"'")
        if not model_id or model_id.startswith(("Provider", "MODEL", "ID")):
            continue
        # Newer OpenCode prints one provider-qualified model id per line. If a
        # future version prints columns, use the first qualified token.
        if "/" not in model_id:
            tokens = model_id.replace("│", " ").replace("┃", " ").split()
            model_id = next((token.strip("`\"',") for token in tokens if "/" in token), "")
        if not model_id.startswith(prefix):
            continue
        if model_id in seen:
            continue
        seen.add(model_id)
        models.append(ProviderModel(id=model_id, name=model_id))
    return models


class OpenCodeCLIAdapter:
    """Adapter for a single provider prefix exposed by the OpenCode CLI.

    Instances are created dynamically by ``discover_opencode_providers``
    rather than subclassed per-prefix — the CLI is the source of truth
    for which providers exist.
    """

    def __init__(
        self,
        cli_prefix: str,
        descriptor_id: str | None = None,
        label: str | None = None,
    ) -> None:
        # ``cli_prefix`` is what we pass to ``opencode models <prefix>`` and
        # what every returned model id is prefixed with on disk. The
        # registry id (``descriptor_id``) may differ when a bare prefix
        # would collide with a first-class HTTP provider — e.g. catalog
        # prefix ``openai`` is registered as ``opencode-openai`` so it
        # doesn't shadow the token-backend OpenAI adapter.
        self.cli_prefix = cli_prefix
        self.provider_id = descriptor_id or cli_prefix
        self.label = label or f"OpenCode · {cli_prefix}"

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            id=self.provider_id,
            label=self.label,
            backend="opencode",
            compatible_backends=["opencode"],
            requires_api_key=False,
            supports_base_url=False,
            supports_model_listing=True,
        )

    async def list_models(self, config: Any) -> list[ProviderModel]:
        output = await _run_cli(["opencode", "models", self.cli_prefix], timeout_s=10.0)
        return _parse_opencode_lines(output, self.cli_prefix) if output else []
