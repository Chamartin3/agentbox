"""Pi backend config generator.

The backend config-generator abstraction was removed when its only subclass
(the Pi generator) was found to be dead code — the executor never
instantiates it. The composed system prompt reaches the workdir via
the workspace generation render pipeline.

This module is kept as a placeholder so the package import path is stable.
"""
