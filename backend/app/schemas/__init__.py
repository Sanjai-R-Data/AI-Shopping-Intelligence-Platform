"""
AI-Powered Multilingual Shopping Intelligence Platform
Pydantic Schemas Package.
"""

from backend.app.schemas.product import (
    ProductBase,
    ProductCreate,
    ProductResponse,
    ProductDetailResponse,
    ProductListResponse,
    ProductCompareItem,
    ProductComparisonResponse,
    RetailerOfferBase,
    RetailerOfferCreate,
    RetailerOfferResponse,
)
from backend.app.schemas.mandate import (
    SpendingMandateBase,
    SpendingMandateCreate,
    SpendingMandateUpdate,
    SpendingMandateResponse,
    PurchaseEvaluationRequest,
    PurchaseEvaluationResponse,
)
from backend.app.schemas.assistant import (
    ShoppingIntent,
    SpecificationRequirement,
    ProductEligibilityItem,
    ProductIntelligence,
    ProductIntelligenceList,
    ComparisonExplanation,
    AssistantQueryRequest,
    AssistantQueryResponse,
)
from backend.app.schemas.checkout import (
    OrderItemBase,
    OrderItemCreate,
    OrderItemResponse,
    PaymentCaptureResponse,
    CheckoutOrderCreate,
    PaymentOrderResponse,
    PaymentHistoryItemResponse,
    PaymentOrderListResponse,
    RetailerRedirectResponse,
)

__all__ = [
    "ProductBase",
    "ProductCreate",
    "ProductResponse",
    "ProductDetailResponse",
    "ProductListResponse",
    "ProductCompareItem",
    "ProductComparisonResponse",
    "RetailerOfferBase",
    "RetailerOfferCreate",
    "RetailerOfferResponse",
    "SpendingMandateBase",
    "SpendingMandateCreate",
    "SpendingMandateUpdate",
    "SpendingMandateResponse",
    "PurchaseEvaluationRequest",
    "PurchaseEvaluationResponse",
    "ShoppingIntent",
    "SpecificationRequirement",
    "ProductEligibilityItem",
    "ProductIntelligence",
    "ProductIntelligenceList",
    "ComparisonExplanation",
    "AssistantQueryRequest",
    "AssistantQueryResponse",
    "OrderItemBase",
    "OrderItemCreate",
    "OrderItemResponse",
    "PaymentCaptureResponse",
    "CheckoutOrderCreate",
    "PaymentOrderResponse",
    "PaymentHistoryItemResponse",
    "PaymentOrderListResponse",
    "RetailerRedirectResponse",
]
