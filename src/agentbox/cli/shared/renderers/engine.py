"""Engine CLI renderer — typed output methods for engine commands."""

from __future__ import annotations

import json as _json
from collections.abc import Sequence

from agentbox.cli.shared.constants import JsonValue
from agentbox.cli.shared.render import Renderer
from agentbox.core.service import RunnerProfile, RunnerProfileStats

# TODO(cli-arch): move to facade export (plan 095 Phase A)
from agentbox.core.engines.providers.base import ProviderDescriptor, ProviderModel

# TODO(cli-arch): move to facade export (plan 095 Phase A)
from agentbox.core.engines.credentials.registry import CredentialMethod

# TODO(cli-arch): move to facade export (plan 095 Phase A)
from agentbox.core.engines.credentials.state import CredentialState


class EngineRenderer(Renderer):
    """Typed render methods for engine contracts — formatting lives here, never in command bodies."""

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

    def profiles_table(self, profiles: list[RunnerProfile]) -> None:
        """Render a table of runner profiles."""
        if not profiles:
            self.warn("No runner profiles found.")
            return

        table = self.table(
            "Runner Profiles",
            "ID", "Name", "Backend", "Provider", "Model",
            "Enabled", "System Default",
        )
        for p in profiles:
            table.add_row(
                p.id, p.name, p.backend,
                p.provider or self.na(""),
                p.model or self.na(""),
                self.check(p.is_enabled),
                self.check(p.is_system_default),
            )
        self.print(table)

    def profiles_json(self, profiles: list[RunnerProfile]) -> None:
        """Render runner profiles as machine-readable JSON."""
        self.con.print(_json.dumps([p.model_dump() for p in profiles], indent=2))

    def profile_detail_json(self, profile: RunnerProfile) -> None:
        """Render a single profile detail as JSON."""
        self.json(profile.model_dump())

    def profile_created(self, profile: RunnerProfile) -> None:
        """Print success message for profile creation, then detail."""
        self.success(f"Created runner profile {profile.id}")
        self.json(profile.model_dump())

    def profile_bound(self, agent_id: str, profile_id: str) -> None:
        """Print success message for agent-to-profile binding."""
        self.success(f"Bound agent {agent_id} to profile {profile_id}")

    def profile_cleared(self, agent_id: str) -> None:
        """Print success message for clearing profile binding."""
        self.success(f"Cleared profile binding for agent {agent_id}")

    def profile_deleted(self, profile_id: str) -> None:
        """Print success message for profile deletion."""
        self.success(f"Deleted runner profile {profile_id}")

    def profile_not_found(self, profile_id: str) -> None:
        """Print error for missing profile."""
        self.error(f"Profile not found: {profile_id}")

    def profile_stats_detail(self, profile_id: str, stats: RunnerProfileStats) -> None:
        """Render stats for a single runner profile."""
        self.kv(
            f"Stats for profile {profile_id}",
            [
                ("Runs", str(stats.runs)),
                ("Succeeded", str(stats.succeeded)),
                ("Failed", str(stats.failed)),
                ("Input Tokens", str(stats.input_tokens)),
                ("Output Tokens", str(stats.output_tokens)),
                ("Cost (USD)", f"${stats.cost_usd:.4f}" if stats.cost_usd else self.na("")),
                ("Avg Duration (ms)", f"{stats.avg_duration_ms:.1f}" if stats.avg_duration_ms else self.na("")),
                ("Last Run", stats.last_run_at or self.na("")),
            ],
        )

    def all_profile_stats_table(self, all_stats: list[RunnerProfileStats]) -> None:
        """Render a table of stats for all runner profiles."""
        if not all_stats:
            self.warn("No profile statistics found.")
            return

        table = self.table(
            "All Runner Profile Stats",
            "Profile ID", "Runs", "Succeeded", "Failed",
            "Input Tokens", "Output Tokens", "Cost (USD)",
        )
        for stats in all_stats:
            table.add_row(
                stats.profile_id,
                str(stats.runs),
                str(stats.succeeded),
                str(stats.failed),
                str(stats.input_tokens),
                str(stats.output_tokens),
                f"${stats.cost_usd:.4f}" if stats.cost_usd else self.na(""),
            )
        self.print(table)

    # ------------------------------------------------------------------
    # Backends
    # ------------------------------------------------------------------

    def backends_table(
        self, backends: Sequence[tuple[str, str, JsonValue, JsonValue]]
    ) -> None:
        """Render a table of registered backend adapters.

        Each row is ``(id, label, default_model, compatible_providers_str)``.
        """
        if not backends:
            self.warn("No backends registered.")
            return

        table = self.table(
            "Runner Backends",
            "ID", "Label", "Default Model", "Compatible Providers",
        )
        for backend_id, label, default_model, compat in backends:
            table.add_row(
                backend_id,
                label,
                str(default_model) if default_model else self.na(""),
                str(compat) if compat else self.na(""),
            )
        self.print(table)

    def backends_json(
        self, backends: Sequence[tuple[str, str, JsonValue, JsonValue]]
    ) -> None:
        """Render registered backends as machine-readable JSON."""
        result: list[dict[str, JsonValue]] = [
            {
                "id": bid,
                "label": label,
                "default_model": default_model,
                "compatible_providers": compat,
            }
            for bid, label, default_model, compat in backends
        ]
        print(_json.dumps(result, indent=2))

    # ------------------------------------------------------------------
    # Providers
    # ------------------------------------------------------------------

    def providers_table(self, descriptors: list[ProviderDescriptor]) -> None:
        """Render a table of provider descriptors."""
        if not descriptors:
            self.warn("No providers found.")
            return

        table = self.table(
            "Providers",
            "ID", "Label", "Backend", "Requires API Key", "Supports Model Listing",
        )
        for desc in descriptors:
            table.add_row(
                desc.id, desc.label, desc.backend,
                self.check(desc.requires_api_key),
                self.check(desc.supports_model_listing),
            )
        self.print(table)

    def provider_models_table(self, provider_id: str, models: list[ProviderModel]) -> None:
        """Render a table of available models for a provider."""
        if not models:
            self.warn(f"No models found for provider {provider_id}.")
            return

        table = self.table(
            f"Models for {provider_id}",
            "ID", "Name", "Context Length",
        )
        for model in models:
            ctx_len = model.context_length
            table.add_row(model.id, model.name or model.id, str(ctx_len) if ctx_len else self.na(""))
        self.print(table)

    def provider_models_not_supported(self, provider_id: str) -> None:
        """Print warning that a provider does not support model listing."""
        self.warn(f"Provider {provider_id} does not support model listing.")

    def provider_not_found(self, provider_id: str) -> None:
        """Print error for missing provider."""
        self.error(f"Provider not found: {provider_id}")

    def provider_models_error(self, error_msg: str) -> None:
        """Print error message for model listing failure."""
        self.error(f"Error fetching models: {error_msg}")

    def provider_refresh_success(self, discovered: list[str]) -> None:
        """Print success message after refreshing opencode providers."""
        self.success(f"Discovered {len(discovered)} opencode provider(s): {', '.join(discovered)}")

    def provider_refresh_none(self) -> None:
        """Print warning when no opencode providers are discovered."""
        self.warn("No opencode providers discovered (binary missing or call failed).")

    # ------------------------------------------------------------------
    # Credentials
    # ------------------------------------------------------------------

    def credential_status_table(self, items: list[CredentialMethod]) -> None:
        """Render a table of credential statuses for all backends."""
        if not items:
            self.dim("No credential backends registered.")
            return

        table = self.table("Credential Status", "Status", "Backend", "Detail")
        for cm in items:
            state = cm.detect()
            table.add_row(self._state_label(state), cm.label, cm.backend)
        self.print(table)

    def credential_unknown_backend(self, name: str) -> None:
        """Print error for unknown credential backend."""
        self.error(f"Unknown backend: {name!r}")

    def credential_already_configured(self) -> None:
        """Print dim message for already-configured credentials."""
        self.dim("Already configured.")

    def credential_no_methods(self) -> None:
        """Print dim message when no credential methods are available."""
        self.dim("No credential methods available.")

    def credential_configured(self, method_label: str) -> None:
        """Print success message after credential configuration."""
        self.success(f"Credential configured via {method_label}")

    def credential_method_warning(self) -> None:
        """Print warning when method ran but credential not detected."""
        self.warn("Method ran but credential not detected. Check manually.")

    def credential_method_failed(self, exc: Exception) -> None:
        """Print error message when credential method fails."""
        self.error(f"Failed: {exc}")

    def credential_no_import_method(self, name: str) -> None:
        """Print error when no import method is available for a backend."""
        self.error(f"No import method available for {name!r}.")

    def credential_dir_removed(self, path: str) -> None:
        """Print success message when a credential directory is removed."""
        self.success(f"Removed: {path}")

    def credential_env_removed(self, env_path: str) -> None:
        """Print success message when env vars are removed."""
        self.success(f"Removed env vars from: {env_path}")

    def credential_cleared(self) -> None:
        """Print success message when all credentials are cleared."""
        self.success("Credentials cleared.")

    def credential_none_found(self, name: str) -> None:
        """Print dim message when no credentials are found for a backend."""
        self.dim(f"No credentials found for {name!r}.")

    def credential_skip_detected(self) -> None:
        """Print dim message when credentials are detected and setup is skipped."""
        self.dim("Credentials detected — skipping. Use `agentbox ops creds clear ...` to reset.")

    def credential_no_backends_registered(self) -> None:
        """Print dim message when no credential backends are registered."""
        self.dim("No credential backends registered.")

    def credential_setup_header(self) -> None:
        """Print the setup header."""
        self.print("\n[bold]Agentbox Credential Setup[/bold]\n")

    def credential_choose_method(self, cm: CredentialMethod) -> None:
        """Print the choose-method prompt header."""
        state = cm.detect()
        state_icon: str = self._state_name_to_style(state)
        self.print(f"\n[{state_icon}]{cm.label}[/{state_icon}] ({cm.backend})")

        if state == CredentialState.PRESENT:
            self.credential_skip_detected()
            return

        methods = cm.methods
        if not methods:
            self.credential_no_methods()
            return

        self.print("  Choose method:")
        for i, m in enumerate(methods):
            self.print(f"    {i + 1}) {m.label}")

    def credential_invalid_choice(self) -> None:
        """Print error for invalid choice."""
        self.error("Invalid choice.")

    def credential_invalid_input(self) -> None:
        """Print error for invalid input."""
        self.error("Invalid input — enter a number, or 's' to skip.")

    def credential_skipped(self) -> None:
        """Print dim message for skipped credential."""
        self.dim("Skipped.")

    def credential_multiple_methods_hint(self) -> None:
        """Print hint when multiple methods are available but not interactive."""
        self.dim("Multiple methods available; use interactive mode.")

    # ------------------------------------------------------------------
    # Credential helpers (private, only used by methods above)
    # ------------------------------------------------------------------

    @staticmethod
    def _state_name_to_style(state: CredentialState) -> str:
        """Map a CredentialState to a Rich style name for inline markup."""
        return {
            CredentialState.PRESENT: "green",
            CredentialState.MISSING: "dim",
            CredentialState.INVALID: "yellow",
        }.get(state, "dim")

    @staticmethod
    def _state_label(state: CredentialState) -> str:
        """Map a CredentialState to a human-readable label."""
        return {
            CredentialState.PRESENT: "PRESENT",
            CredentialState.MISSING: "MISSING",
            CredentialState.INVALID: "INVALID",
        }.get(state, "UNKNOWN")
