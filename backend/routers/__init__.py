"""Routers package - API 路由"""
from .observation import router as observation_router
from .image import router as image_router

__all__ = [
    "observation_router",
]
