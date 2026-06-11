"""Resource-scoped data layer.

Submodules:
- crud/ : ResourcesMixin — versioned resource repository CRUD (split into
  ``_repo``, ``_versions``, ``_blobs`` sub-mixins)
- shared/ : SharedResourcesMixin — versioned shared resource persistence
  (split into ``_models``, ``hash``, ``lookup``, ``write`` sub-modules)
- bindings: ResourceBindingsMixin — prompt embedding + workspace file bindings
"""
