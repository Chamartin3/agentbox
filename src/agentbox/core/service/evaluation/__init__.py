"""Evaluation service package (plan 093) — run/agent analytics.

Import ``EvaluationService`` from ``agentbox.core.service`` (the facade).
Re-exports ``ActivityRange`` and ``since_iso`` so callers need not reach into
``core.db.feedback.types`` directly.
"""
from agentbox.core.db.feedback.types import ActivityRange as ActivityRange
from agentbox.core.db.feedback.types import since_iso as since_iso
from agentbox.core.service.evaluation.service import EvaluationService as EvaluationService
