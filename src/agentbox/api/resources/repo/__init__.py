"""/repo-resources — sub-routers assembly.

Each route module registers endpoints on its own ``APIRouter``;
this file assembles them under the same prefix.
"""

from fastapi import APIRouter

from agentbox.api.resources.repo.create import create_router
from agentbox.api.resources.repo.delete_ import delete_router
from agentbox.api.resources.repo.inspect import inspect_router
from agentbox.api.resources.repo.list_ import list_router

router = APIRouter()
router.include_router(list_router)
router.include_router(create_router)
router.include_router(inspect_router)
router.include_router(delete_router)
