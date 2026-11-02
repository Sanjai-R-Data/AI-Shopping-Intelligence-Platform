# Gemini AI Integration Guide (Phase 3 & 3.1)

**Platform:** AI-Powered Multilingual Shopping Intelligence Platform  
**Tagline:** Discover smarter. Compare deeper. Spend responsibly.  
**Version:** 1.1.0 (Phase 3.1 Live Integration & Bug Fixes Milestone)  
**Configured AI Model:** `gemini-3.8-flash`  
**SDK:** `google-genai` (v2.34.0)

---

## 1. Overview & Architectural Role

The Gemini AI integration forms the cognitive layer of the AI-Powered Multilingual Shopping Intelligence Platform. Rather than acting as an unconstrained autonomous agent, Gemini operates under strict architectural guardrails.

### The Core Architectural Guardrail

```text
┌────────────────────────────────────────────────────────────────────────┐
│   "AI Suggests  →  Backend Validates  →  User Approves  →  PayPal Processes"   │
└────────────────────────────────────────────────────────────────────────┘
```

1. **AI Suggests:** Gemini parses complex natural-language queries into structured shopping parameters, evaluates hardware/spec suitability against intended workflows, and explains technical trade-offs.
2. **Backend Validates:** The backend controls all product searching (Channel3 aggregator / local catalog), strictly evaluates spending eligibility via the deterministic `SpendingPolicyEngine`, and verifies hardware specifications and currency boundaries via deterministic logic.
3. **User Approves:** The user explicitly inspects offers, intelligence rationales, eligibility breakdowns, and mandate statuses before initiating any checkout.
4. **PayPal Processes:** In a future phase, orders and captures occur strictly between the backend and PayPal Sandbox, isolated from AI inference.

---

## 2. Model Selection & Configuration

### Configured Model
- **Primary Model:** `gemini-3.8-flash`
- **Thinking Configuration:** `thinking_level = "medium"` using `types.ThinkingConfig(thinking_level=types.ThinkingLevel.MEDIUM)` to allow reasoning over complex technical trade-offs while maintaining fast response times.
- **Network Deadline:** Configured to `30.0` seconds. In the `google-genai` SDK, `types.HttpOptions(timeout=...)` expects integer milliseconds, converted as `int(timeout_seconds * 1000)`.

### Centralized Settings (`backend/app/core/config.py`)

All Gemini parameters are managed through Pydantic Settings with zero hardcoding:

```python
GEMINI_API_KEY: SecretStr | None = None
GEMINI_MODEL: str = "gemini-3.8-flash"
GEMINI_TIMEOUT_SECONDS: float = 30.0
GEMINI_THINKING_LEVEL: str = "medium"
```

All credentials are typed as `SecretStr`, preventing accidental exposure in logs, serialization, or error traces.

---

## 3. Phase 3.1 Live Integration Fixes

### 3.1. `additionalProperties` Rejection in Gemini Developer API Mode
- **Root Cause:** In Gemini Developer API mode (`google-genai` calling `generativelanguage.googleapis.com`), Google's schema parser strictly prohibits `"additionalProperties"` in JSON schemas. In OpenAPI 3.0, Pydantic's `dict[str, str]` generates `"additionalProperties": {"type": "string"}`. When Gemini receives this schema in `response_schema`, it rejects the request with:
  ```text
  additionalProperties is only supported in Gemini Enterprise Agent Platform mode, not in Gemini Developer API mode.
  ```
- **Architectural Solution:**
  1. Replaced `dict[str, str]` with a dedicated Pydantic model: `list[SpecificationRequirement]`.
  2. Each `SpecificationRequirement` defines explicit scalar fields:
     - `name: str` (e.g., `"ram"`, `"storage"`, `"gpu"`)
     - `value: str` (e.g., `"16GB"`, `"512GB"`)
     - `raw_spec: str` (e.g., `"at least 16GB RAM"`)
     - `min_value: float | None` (e.g., `16.0`)
     - `unit: str | None` (e.g., `"GB"`, `"TB"`)
     - `is_hard_requirement: bool` (e.g., `True` for "at least 16GB", `False` for "preferably 16GB")
  3. Created `SpecificationList` (a subclass of `list[SpecificationRequirement]`) that provides dictionary-style `.get(key, default)` lookups, ensuring 100% backward compatibility with existing code.
  4. Added Pydantic field validators to seamlessly accept both list and dict formats during deserialization.
  5. The resulting OpenAPI schema contains zero `additionalProperties`, satisfying the Gemini Developer API mode specification.

### 3.2. Specification Extraction & Disambiguation
- **Hard Requirements vs Preferences:** Queries containing imperative constraints ("at least", "minimum", "not less than", "must have") are tagged with `is_hard_requirement = True`. Soft preferences ("preferably", "ideally", "if possible") are placed in `preferred_specs`.
- **RAM vs Storage/SSD Disambiguation:** Prompt engineering and fallback regex explicitly separate primary system memory (`ram`) from secondary persistent storage (`storage` / `ssd`), preventing "512GB SSD" from being conflated with RAM.
- **Enhanced Multilingual Fallback Intent Extractor:**
  If Gemini is unavailable or rate-limited, `_fallback_rule_based_intent` uses regex to extract:
  - English: `"at least 16GB RAM"`, `"512 GB SSD"`, `"under $1000"`
  - Tamil: `"16GB ரேம்"`, `"₹70000க்குள்"`
  - Spanish: `"al menos 16GB RAM"`, `"menos de 1000€"`
  - French: `"au moins 16GB RAM"`, `"moins de 1000€"`

### 3.3. Deterministic Product Eligibility & Currency Boundary
To prevent AI hallucinations regarding budget and hardware compliance:
1. **Spec Verification:** `evaluate_product_eligibility` parses RAM and storage from product specifications, titles, and descriptions.
2. **Deterministic Status Classification:**
   - `QUALIFIED`: All hard requirement specifications verified from product data, and offer price matches user currency and budget.
   - `CURRENCY_MISMATCH`: Product price currency differs from query budget currency (e.g., USD offer against INR budget). Without an authoritative real-time FX rate, the system refuses to assume an arbitrary rate or claim the product satisfies an INR budget.
   - `UNVERIFIED_SPECS`: Product metadata does not explicitly state the required hardware specification.
   - `EXCLUDED`: Product fails a hard requirement (e.g., verified RAM of 8GB < 16GB required) or price exceeds budget in matching currency.
3. **Partitioned Collections:** `AssistantQueryResponse` provides:
   - `qualified_product_ids: list[str]`
   - `excluded_product_ids: list[str]`
   - `unverified_product_ids: list[str]`
   - `currency_mismatch_product_ids: list[str]`
   - `eligibility_details: list[ProductEligibilityItem]`

### 3.4. Assistant Summary Consistency
The conversational response must never contradict the backend evaluation:
- Candidate counts must match the actual product list.
- Unqualified or currency-mismatched products must never be described as "qualifying under your budget".
- When products have different currencies, an explicit Currency Notice is presented with exact amounts.

---

## 4. Structured Data Contracts

### 4.1. `SpecificationRequirement` & `SpecificationList`
```python
class SpecificationRequirement(BaseModel):
    name: str
    value: str
    raw_spec: str = ""
    min_value: float | None = None
    unit: str | None = None
    is_hard_requirement: bool = True
```

### 4.2. `ShoppingIntent`
```json
{
  "query": "I need a laptop for AI and machine learning under ₹70000 with at least 16GB RAM",
  "category": "laptop",
  "intended_use": ["ai", "machine_learning"],
  "max_budget": 70000.0,
  "min_budget": null,
  "currency": "INR",
  "required_specs": [
    {
      "name": "ram",
      "value": "16GB",
      "raw_spec": "at least 16GB RAM",
      "min_value": 16.0,
      "unit": "GB",
      "is_hard_requirement": true
    }
  ],
  "preferred_specs": [],
  "brand_preferences": [],
  "excluded_brands": [],
  "detected_language": "en",
  "clarification_required": false,
  "clarification_questions": []
}
```

### 4.3. `ProductEligibilityItem`
```json
{
  "product_id": "c3-prod-1",
  "product_name": "HP Pavilion 15.6 Laptop",
  "status": "CURRENCY_MISMATCH",
  "is_qualified": false,
  "reasons": [
    "Currency notice: Offer is in USD ($649.99), user specified INR. Cannot guarantee budget fit without live FX conversion."
  ],
  "verified_specs": {
    "ram": "16GB"
  },
  "unverified_specs": []
}
```

### 4.4. `ProductIntelligence`
```json
{
  "product_id": "prod-101",
  "product_name": "DevBook Pro 16",
  "suitability": "EXCELLENT",
  "strengths": ["32 GB RAM allows comfortable local model inference"],
  "weaknesses": ["Dedicated GPU consumes significant battery"],
  "intended_use_fit": "Optimal for local LLM experimentation and data science.",
  "missing_information": [],
  "value_for_money_rating": 4.5,
  "recommendation_rationale": "Meets user hardware and budget criteria without compromise."
}
```

### 4.5. `ComparisonExplanation`
```json
{
  "summary": "Comparing DevBook Pro 16 against UltraSlim X for coding and ML.",
  "key_differences": ["DevBook has 32GB RAM vs UltraSlim's 16GB", "DevBook includes discrete RTX 4060 GPU"],
  "tradeoffs": ["UltraSlim is 40% lighter and costs $300 less"],
  "overall_winner": "DevBook Pro 16",
  "best_value_pick": "UltraSlim X",
  "currency_consistency_warning": null
}
```

---

## 5. Non-Bypassable Spending Policy Boundary

A paramount security requirement of the platform is that **the AI cannot bypass or alter spending policies**:

1. **Deterministic Authority:** The `SpendingPolicyEngine` runs deterministically in Python. Its mathematical evaluations (`unit_price <= max_item_price`, `remaining_budget >= total_amount`) cannot be influenced by LLM reasoning or prompt injection.
2. **Enthusiastic AI Recommendations Blocked:** If Gemini recommends an expensive product that exceeds the user's spending limit, `AssistantService` returns:
   - `mandate_evaluation.decision = "BLOCKED"`
   - `mandate_evaluation.reasons = ["Unit price $1,299.99 exceeds max item price $100.00"]`
   - The conversational reply highlights the policy blockage.
3. **Mandate Immutability:** No prompt can instruct Gemini to alter database records or modify mandate spending ceilings.

---

## 6. Resilience & Graceful Degradation

If the Gemini API encounters upstream errors, rate limits, timeouts, or temporary 503 high demand:
1. **Rule-Based Fallback:** `AssistantService._fallback_rule_based_intent` extracts categories, currencies (`$`, `₹`, `€`, `£`), numbers (`under 70000`, `below $100`), RAM constraints, and storage deterministically without crashing.
2. **Zero Interruption:** Real products are still queried from Channel3 or the database and presented to the user.
3. **Status Transparency:** The response sets `is_ai_degraded = True` with the exact diagnostic reason in `degraded_reason`.
4. **Deterministic Synthesis:** A structured deterministic message is rendered rather than failing the request.

---

## 7. Comprehensive Verification Matrix (50 Gemini Tests)

| Test Category | Test Count | Description | Result |
| :--- | :--- | :--- | :--- |
| **Category A: Client Init & Auth** | 3 tests | Initialization, default configuration, missing API key handling | ALL PASSED |
| **Category B: API Error Handling** | 6 tests | 401/403 auth, 429 rate limit, timeout, 503 unavailable, malformed JSON, empty response | ALL PASSED |
| **Category C: Intent Extraction** | 7 tests | Laptop ML, headphones travel, INR budget, Tamil, Spanish, French, clarification | ALL PASSED |
| **Category D: Product Intelligence** | 3 tests | Grounded evidence analysis, missing specs transparency, ID hallucination filtering | ALL PASSED |
| **Category E: Comparison Explanation** | 2 tests | Grounded comparison, mixed currency safeguard warning | ALL PASSED |
| **Category F: Assistant Service Flow** | 2 tests | Session initialization, conversation context preservation across turns | ALL PASSED |
| **Category G: Security & Policy** | 2 tests | Spending policy immune to AI bypass, mandate limits immutable from AI | ALL PASSED |
| **Category H: Schema Compatibility (Phase 3.1)** | 4 tests | Zero `additionalProperties` in `ShoppingIntent`, `SpecificationRequirement`, `SpecificationList` compatibility, dict coercion | ALL PASSED |
| **Category I: Intent Specification Parsing (Phase 3.1)** | 5 tests | Hard requirement vs preference, RAM vs storage disambiguation, multilingual specs (Tamil, Spanish, French) | ALL PASSED |
| **Category J: Deterministic Eligibility (Phase 3.1)** | 8 tests | Qualified RAM/budget, excluded under-spec RAM, excluded over-budget, unverified specs, currency mismatch (INR vs USD), title extraction, partitioned collection consistency | ALL PASSED |
| **Category K: Summary Consistency (Phase 3.1)** | 5 tests | Zero falsely qualified claims, currency notice formatting, truthful product count reporting, empty results handling, degradation transparency | ALL PASSED |
| **Total Gemini Tests** | **50 tests** | **Complete coverage of AI client, schemas, orchestrator, and security** | **100% PASSED** |
