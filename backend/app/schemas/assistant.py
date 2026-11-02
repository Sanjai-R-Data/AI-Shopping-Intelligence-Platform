"""
AI-Powered Multilingual Shopping Intelligence Platform
Pydantic v2 Schemas for Gemini AI Assistant & Shopping Intelligence.
Defines structured schemas for shopping intent extraction, grounded product analyses,
multi-product comparisons, and session-scoped conversational queries.
"""

from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.schemas.product import ProductResponse


class SpecificationRequirement(BaseModel):
    """
    Structured specification requirement extracted from user query.
    Explicit typed objects prevent arbitrary dictionary schema generation,
    strictly adhering to Gemini Developer API structured-output constraints.
    """
    name: str = Field(..., description="Specification name in lower snake_case (e.g. 'ram', 'storage', 'gpu')")
    value: str = Field(..., description="Specification requirement or value (e.g. '16 GB or more', '512 GB SSD')")
    raw_spec: str = Field(default="", description="Original query fragment containing the specification requirement")
    min_value: float | None = Field(default=None, description="Numeric minimum constraint if applicable (e.g. 16.0 for 16GB)")
    unit: str | None = Field(default=None, description="Unit of measurement (e.g. 'GB', 'TB', 'inch')")
    is_hard_requirement: bool = Field(default=True, description="True if explicit hard requirement ('at least', 'minimum', 'must have')")


class SpecificationList(list):
    """
    Custom list of SpecificationRequirement that supports dictionary-style .get(name) lookup
    while retaining standard list behavior and zero additionalProperties in JSON Schema.
    """
    def get(self, key: str, default: Any = None) -> Any:
        for item in self:
            if hasattr(item, "name") and item.name.lower() == key.lower():
                return item.value
            elif isinstance(item, dict) and item.get("name", "").lower() == key.lower():
                return item.get("value")
        return default


class ShoppingIntent(BaseModel):
    """
    Structured shopping intent extracted from natural-language user queries.
    Captures category, explicit budgets, specs, brands, and multilingual metadata.
    """
    query: str = Field(..., description="Original raw user input query")
    category: str = Field(default="general", description="Identified product taxonomy or category (e.g. laptop, headphones)")
    intended_use: list[str] = Field(default_factory=list, description="Intended usage or workloads (e.g. machine_learning, gaming)")
    max_budget: float | None = Field(default=None, ge=0, description="Explicit maximum budget limit, if stated")
    min_budget: float | None = Field(default=None, ge=0, description="Explicit minimum budget limit, if stated")
    currency: str = Field(default="USD", min_length=3, max_length=3, description="ISO-4217 3-letter currency code (e.g. USD, INR)")
    required_specs: list[SpecificationRequirement] = Field(
        default_factory=list,
        description="Explicit hard requirements (e.g. [{'name': 'ram', 'value': '16 GB or more'}])",
    )
    preferred_specs: list[SpecificationRequirement] = Field(
        default_factory=list,
        description="Soft preferred specifications",
    )
    brand_preferences: list[str] = Field(default_factory=list, description="Preferred brands (e.g. ['Apple', 'Anker'])")
    excluded_brands: list[str] = Field(default_factory=list, description="Explicitly excluded or disliked brands")
    detected_language: str = Field(default="en", description="Detected language code (e.g. en, ta, es, fr)")
    clarification_required: bool = Field(default=False, description="True if query is excessively ambiguous")
    clarification_prompt: str | None = Field(default=None, description="Suggested clarification question for the user")
    clarification_questions: list[str] = Field(default_factory=list, description="Suggested clarification questions for the user")

    @field_validator("required_specs", "preferred_specs", mode="before")
    @classmethod
    def _coerce_specs(cls, v: Any) -> list[Any]:
        """Coerce dictionary or string input into list of SpecificationRequirement objects."""
        if isinstance(v, dict):
            items = []
            for k, val in v.items():
                if isinstance(val, dict):
                    items.append({"name": k, **val})
                elif isinstance(val, SpecificationRequirement):
                    items.append(val)
                else:
                    items.append({"name": k, "value": str(val)})
            return items
        if isinstance(v, list):
            res = []
            for item in v:
                if isinstance(item, str):
                    res.append({"name": "spec", "value": item})
                else:
                    res.append(item)
            return res
        return []

    @field_validator("required_specs", "preferred_specs", mode="after")
    @classmethod
    def _wrap_specs(cls, v: Any) -> SpecificationList:
        return SpecificationList(v)

    @property
    def required_specs_dict(self) -> dict[str, str]:
        """Convenience map of normalized spec name to value."""
        return {s.name.lower(): s.value for s in self.required_specs}

    @property
    def preferred_specs_dict(self) -> dict[str, str]:
        """Convenience map of preferred spec name to value."""
        return {s.name.lower(): s.value for s in self.preferred_specs}


class ProductIntelligence(BaseModel):
    """
    Grounded product intelligence analysis for a single retrieved product.
    Strictly grounded on actual evidence: no invented specifications, prices, or ratings.
    """
    product_id: str = Field(..., description="Canonical product ID matching retrieved evidence")
    product_name: str = Field(..., description="Product commercial name")
    suitability: str = Field(..., description="Suitability assessment for user's intended use")
    strengths: list[str] = Field(default_factory=list, description="Key evidenced strengths")
    weaknesses: list[str] = Field(default_factory=list, description="Evidenced limitations or weaknesses")
    intended_use_advantages: list[str] = Field(default_factory=list, description="Specific advantages for user's workload")
    compromises_or_disadvantages: list[str] = Field(default_factory=list, description="Trade-offs or compromises")
    value_for_money_explanation: str = Field(default="", description="Objective assessment of price versus capabilities")
    missing_information: list[str] = Field(default_factory=list, description="Crucial specifications not provided by merchant")
    recommendation_rationale: str = Field(default="", description="Summary recommendation justification")


class ProductIntelligenceList(BaseModel):
    """Container for batch structured output of product analyses."""
    items: list[ProductIntelligence] = Field(default_factory=list)


class ComparisonExplanation(BaseModel):
    """
    Grounded multi-product comparison summary and intended-use recommendation.
    """
    summary: str = Field(..., description="High-level overview of the compared items")
    performance_differences: list[str] = Field(default_factory=list, description="Evidenced technical differences")
    key_differences: list[str] = Field(default_factory=list, description="Key evidenced differences")
    value_tradeoffs: str = Field(default="", description="Analysis of price spreads and value trade-offs")
    tradeoffs: list[str] = Field(default_factory=list, description="Detailed trade-off points")
    best_choice_for_use_case: str = Field(default="", description="Recommended product for the specific user need")
    overall_winner: str | None = Field(default=None, description="Overall winning product for use case")
    best_value_pick: str | None = Field(default=None, description="Best value for money product")
    missing_specs_notes: list[str] = Field(default_factory=list, description="Noteworthy missing specs in comparison")
    currency_notes: str | None = Field(default=None, description="Notes on currency alignment or cross-currency cautions")
    currency_consistency_warning: str | None = Field(default=None, description="Warning if cross-currency comparisons lack FX conversion")


class AssistantQueryRequest(BaseModel):
    """Request payload for the conversational AI shopping assistant endpoint."""
    session_id: str = Field(..., description="Unique shopping session identifier")
    query: str = Field(..., min_length=1, max_length=1000, description="Natural-language shopping query or follow-up question")
    conversation_context: list[dict[str, str]] = Field(
        default_factory=list,
        description="Bounded prior messages in this session [{'role': 'user'|'assistant', 'content': '...'}]",
    )


class ProductEligibilityItem(BaseModel):
    """
    Detailed deterministic eligibility evaluation for a retrieved product
    against hard specifications (e.g. at least 16GB RAM) and budget currency constraints.
    """
    product_id: str
    product_name: str
    status: str = Field(..., description="QUALIFIED, EXCLUDED, UNVERIFIED_SPECS, or CURRENCY_MISMATCH")
    is_qualified: bool
    reasons: list[str] = Field(default_factory=list)
    verified_specs: dict[str, Any] = Field(default_factory=dict)
    unverified_specs: list[str] = Field(default_factory=list)


class AssistantQueryResponse(BaseModel):
    """Comprehensive response from the AI shopping assistant."""
    success: bool = True
    session_id: str
    intent: ShoppingIntent
    products: list[ProductResponse] = Field(default_factory=list, description="Retrieved canonical products")
    qualified_product_ids: list[str] = Field(default_factory=list, description="IDs of products satisfying all hard requirements and budget")
    excluded_product_ids: list[str] = Field(default_factory=list, description="IDs of products failing budget or specification requirements")
    unverified_product_ids: list[str] = Field(default_factory=list, description="IDs of products with missing/unverifiable hard specifications")
    currency_mismatch_product_ids: list[str] = Field(default_factory=list, description="IDs of products whose currency cannot be compared directly against user budget")
    eligibility_details: list[ProductEligibilityItem] = Field(default_factory=list, description="Deterministic eligibility breakdown for each product")
    ai_analyses: list[ProductIntelligence] = Field(default_factory=list, description="Grounded AI product intelligence")
    assistant_message: str = Field(..., description="Conversational explanation and guidance for the user")
    mandate_evaluation: dict[str, Any] | None = Field(
        default=None,
        description="Authoritative deterministic spending mandate policy result",
    )
    is_ai_degraded: bool = Field(default=False, description="True if AI reasoning fell back due to provider unavailability")
    degraded_reason: str | None = Field(default=None, description="Explanation if AI reasoning was degraded")

