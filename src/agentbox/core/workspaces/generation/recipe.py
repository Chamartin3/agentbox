"""Recipe value type — re-exported from agentbox.core.data.workenv.

The loader functions (``load_recipe``, ``list_recipes``, ``backend_for_engine``)
live in ``agentbox.core.engines.backends.recipe_loader`` because they need the
backend registry; keeping them here would create a cycle.
"""

from __future__ import annotations

from agentbox.core.data.workenv import Recipe as Recipe

__all__ = ["Recipe"]
