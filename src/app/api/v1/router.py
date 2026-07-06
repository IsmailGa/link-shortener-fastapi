from fastapi import APIRouter

from app.api.v1 import auth, health, links, stats

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(auth.router)
api_v1_router.include_router(links.router)
api_v1_router.include_router(stats.router)
api_v1_router.include_router(health.router)
