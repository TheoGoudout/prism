from fastapi import APIRouter

from app.api.routes import (
    ai,
    integrations,
    login,
    metrics,
    oauth,
    private,
    users,
    utils,
    workspaces,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(workspaces.router)
api_router.include_router(integrations.router)
api_router.include_router(oauth.router)
api_router.include_router(metrics.router)
api_router.include_router(ai.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
