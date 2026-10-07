from fastapi import APIRouter

from app.api.v1 import (
    ai,
    approvals,
    auth,
    content,
    dashboard,
    design,
    knowledge,
    organizations,
    storage,
    topics,
    trends,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(organizations.router)
api_router.include_router(knowledge.router)
api_router.include_router(trends.router)
api_router.include_router(topics.router)
api_router.include_router(topics.rules_router)
api_router.include_router(content.router)
api_router.include_router(design.router)
api_router.include_router(approvals.router)
api_router.include_router(storage.router)
api_router.include_router(ai.router)
api_router.include_router(dashboard.router)
