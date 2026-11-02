"""
AI-Powered Multilingual Shopping Intelligence Platform
Services Package.
"""

from backend.app.services.product_service import ProductService
from backend.app.services.policy_engine import SpendingPolicyEngine
from backend.app.services.channel3_client import Channel3Client, Channel3Error
from backend.app.services.channel3_normalizer import Channel3Normalizer
from backend.app.services.gemini_client import (
    GeminiClient,
    GeminiError,
    GeminiAuthError,
    GeminiRateLimitError,
    GeminiTimeoutError,
    GeminiUnavailableError,
    GeminiResponseError,
)
from backend.app.services.assistant_service import AssistantService

__all__ = [
    "ProductService",
    "SpendingPolicyEngine",
    "Channel3Client",
    "Channel3Normalizer",
    "Channel3Error",
    "GeminiClient",
    "GeminiError",
    "GeminiAuthError",
    "GeminiRateLimitError",
    "GeminiTimeoutError",
    "GeminiUnavailableError",
    "GeminiResponseError",
    "AssistantService",
]
