"""
AI-Powered Multilingual Shopping Intelligence Platform
API Package.
"""

from backend.app.api.health import router as health_router
from backend.app.api.products import router as products_router
from backend.app.api.mandates import router as mandates_router
from backend.app.api.assistant import router as assistant_router

__all__ = ["health_router", "products_router", "mandates_router", "assistant_router"]
