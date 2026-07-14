"""Central resource repository.

DB-backed, versioned repository of resources (documents, folders, skills)
that replaces per-agent TOML declarations. Bytes live in the DB
(``resource_blobs``); the host filesystem is no longer required.
"""
