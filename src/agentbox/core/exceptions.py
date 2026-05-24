"""Domain exceptions raised by the ``core`` layer.

Services and the executor raise these (or subclasses) instead of bare
``ValueError`` / ``Exception``. API/HTTP layers map them to status codes
at the boundary; tests assert against the specific class rather than a
substring of the error message.
"""

from __future__ import annotations


class AgentboxError(Exception):
    """Base class for all agentbox-domain errors."""


# --- Configuration / authoring errors ------------------------------------


class ConfigurationError(AgentboxError):
    """Operator/authoring mistake in agent or runner config."""


class ResourceSchemaError(ConfigurationError):
    """A repo_resource referenced an unknown or invalid schema."""


class InconsistentSchemaError(ConfigurationError):
    """Output schema fails the internal consistency check."""


# --- Backend selection / execution ---------------------------------------


class BackendSelectionError(AgentboxError):
    """No backend adapter could be selected for the requested agent."""


class RunSetupError(AgentboxError):
    """Failure preparing a run (workdir, resources, prompt composition)."""


class SnapshotError(AgentboxError):
    """Failure persisting a per-run snapshot (resource, mcp, runner)."""


class WebhookDeliveryError(AgentboxError):
    """Failure delivering a completion webhook."""


# --- Workspaces / prompts / agents ---------------------------------------


class WorkspaceError(AgentboxError):
    """Workspace registry, permission, or sync failure."""


class PromptVersionError(AgentboxError):
    """Prompt versioning operation failed (draft / publish / rollback)."""


class AgentNotFoundError(AgentboxError):
    """Requested agent id does not exist."""
