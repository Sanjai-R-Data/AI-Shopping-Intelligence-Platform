"""
AI-Powered Multilingual Shopping Intelligence Platform
Pydantic Schemas for Products, Retailer Offers, and Comparisons.
"""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


# -------------------------------------------------------------------------
# Retailer Offer Schemas
# -------------------------------------------------------------------------

class RetailerOfferBase(BaseModel):
    retailer_name: str = Field(..., description="Retailer merchant name (e.g. Amazon, BestBuy)")
    price: float = Field(..., gt=0, description="Offered purchase price")
    currency: str = Field(default="USD", min_length=3, max_length=3, description="ISO-4217 3-letter currency code")
    product_url: str = Field(..., description="Direct outbound product listing URL")
    availability: str = Field(default="IN_STOCK", description="Stock availability status")
    compare_at_price: float | None = Field(default=None, description="Original list price before discount")
    is_synthetic: bool = Field(default=True, description="Whether this offer is synthetic demo data")


class RetailerOfferCreate(RetailerOfferBase):
    product_id: str | None = None
    provider_offer_id: str | None = None


class RetailerOfferResponse(RetailerOfferBase):
    id: str
    product_id: str
    created_at: datetime
    retrieved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------------------
# Product Schemas
# -------------------------------------------------------------------------

class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Product commercial name")
    brand: str = Field(..., min_length=1, max_length=128, description="Manufacturer brand name")
    category: str = Field(..., min_length=1, max_length=128, description="Primary product taxonomy category")
    description: str = Field(default="", description="Detailed marketing & technical description")
    specifications: dict[str, Any] = Field(default_factory=dict, description="Structured technical specifications")
    image_url: str | None = Field(default=None, max_length=512, description="Product image asset URL")
    is_synthetic: bool = Field(default=True, description="Whether this product is synthetic demo data")
    provider: str = Field(default="synthetic", description="Originating provider (e.g. synthetic, channel3)")
    provider_product_id: str | None = Field(default=None, description="Provider-assigned product identifier")
    rating: float | None = Field(default=None, ge=0.0, le=5.0, description="Average validated user rating score (0.0 to 5.0)")
    rating_count: int | None = Field(default=None, ge=0, description="Total count of customer reviews/ratings")
    data_quality_warnings: list[str] = Field(default_factory=list, description="Data quality or taxonomy warnings identified during ingestion")


class ProductCreate(ProductBase):
    offers: list[RetailerOfferCreate] = Field(default_factory=list, description="Initial retailer offers")


class ProductResponse(ProductBase):
    id: str
    created_at: datetime
    lowest_price: float | None = None
    offers: list[RetailerOfferResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ProductDetailResponse(ProductResponse):
    lowest_price_retailer: str | None = None
    total_offers: int = 0


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# -------------------------------------------------------------------------
# Comparison Schemas
# -------------------------------------------------------------------------

class ProductCompareItem(BaseModel):
    id: str
    name: str
    brand: str
    category: str
    image_url: str | None = None
    lowest_price: float | None = None
    currency: str = "USD"
    specifications: dict[str, Any] = Field(default_factory=dict)
    offers: list[RetailerOfferResponse] = Field(default_factory=list)
    best_offer_retailer: str | None = None
    overall_availability: str = "IN_STOCK"
    is_synthetic: bool = True
    provider: str = "synthetic"
    provider_product_id: str | None = None
    rating: float | None = None
    rating_count: int | None = None
    data_quality_warnings: list[str] = Field(default_factory=list)


class ProductComparisonResponse(BaseModel):
    products: list[ProductCompareItem]
    compared_count: int
    comparison_matrix: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Attribute-based comparison matrix mapping specification keys to product values",
    )
    price_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="High-level price metrics including lowest price across products and price ranges",
    )
