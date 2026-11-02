# BUYWISE AI — Frontend Implementation & Architecture Audit

> **System:** BUYWISE AI — AI-Powered Multilingual Shopping Intelligence Platform  
> **Tagline:** Discover smarter. Compare deeper. Spend responsibly.  
> **Audit Milestone:** Phase 1 — Repository and API Audit (Read-Only)  
> **Timestamp:** November 2026  
> **Target Frontend Stack:** HTML5, CSS3, Vanilla JavaScript (ES Modules), Tailwind CSS CDN  
> **Backend Architecture:** FastAPI, SQLAlchemy 2.0, SQLite (WAL mode), Pydantic v2, Google Gemini API, Channel3 API, PayPal Orders v2 Sandbox

---

## 1. Executive Summary

This audit evaluates the readiness of the existing **AI-Powered Shopping Intelligence Platform** backend to support the new **BUYWISE AI** frontend design and user experience. 

BUYWISE AI is designed as a hybrid SaaS platform combining:
1. **A Personal Shopping Copilot:** Grounded conversational intent extraction, product discovery, and trade-off analysis.
2. **A Financial Governance Engine:** Deterministic spending mandate enforcement and purchase eligibility classification.
3. **A Dual-Track Checkout Gateway:** PayPal Orders v2 Sandbox checkout for internal demonstration items, coupled with structured external retailer redirection for live Channel3 marketplace items.

The backend is mature and feature-complete, with **170 passing unit/integration tests (100% pass rate)**. The frontend directory (`frontend/`) is currently empty. This document provides a strict, evidence-based audit of backend capabilities, schema boundaries, security invariants, data quality rules, and necessary frontend integration patterns without modifying existing application source code.

---

## 2. Backend Inventory & Architectural State

### 2.1 Backend Core Structure

| Layer | Component Path | Current State | Notes |
| :--- | :--- | :--- | :--- |
| **Configuration** | `backend/app/core/config.py` | Complete | Centralized Pydantic `Settings`. Enforces PayPal Sandbox URL guardrail. |
| **Database** | `backend/app/core/database.py` | Complete | SQLite with WAL mode, foreign keys, busy timeout, connection pooling. `ensure_schema_compatibility` handles dynamic column alignment. |
| **Error Handling** | `backend/app/core/errors.py` | Complete | RFC 9457 Problem Details (`application/problem+json`). Supports structured error objects in `detail`. |
| **Seed Catalog** | `backend/app/core/seed.py` | Complete | 18 synthetic demo products with multi-retailer offers (`Electronics`, `Audio`, `Wearables`, `Computing`, `Smart Home`). |
| **Product Models** | `backend/app/models/shopping.py` | Complete | `Product`, `RetailerOffer`, `ShoppingSession`, `SpendingMandate`. Cascade protections active. |
| **Payment Models** | `backend/app/models/payment.py` | Complete | `PaymentOrder`, `OrderItem`, `PaymentCapture`. Non-bypassable state machine, Decimal precision, idempotency constraints. |
| **Product Service** | `backend/app/services/product_service.py` | Complete | Catalog search, pagination, live Channel3 search, product details, multi-product comparison matrix. |
| **Channel3 Client** | `backend/app/services/channel3_client.py` | Complete | HTTPX client connecting to `https://api.channel3.ai/v1/products/search`. Normalizes products & retailer offers. |
| **Gemini Client** | `backend/app/services/gemini_client.py` | Complete | Structured output schema generation (`ShoppingIntent`, `ProductIntelligence`). Supports English, Tamil, Spanish, French fallback. |
| **Assistant Service**| `backend/app/services/assistant_service.py` | Complete | Pipeline orchestrator: Intent $\rightarrow$ Product Search $\rightarrow$ Eligibility $\rightarrow$ Mandate Evaluation $\rightarrow$ AI Guidance. |
| **Spending Policy** | `backend/app/services/policy_engine.py` | Complete | Deterministic purchase policy verification (`ALLOWED` vs `BLOCKED`). Independent of LLM reasoning. |
| **PayPal Client** | `backend/app/services/paypal_client.py` | Complete | PayPal Orders v2 REST client. Thread-safe OAuth token cache, 300s expiry buffer, sandbox URL enforcement. |
| **Checkout Service**| `backend/app/services/checkout_service.py` | Complete | 2-phase decoupled transactions, dual-track purchase routing, timeout reconciliation probe, authoritative capture verification. |

---

## 3. API Capability Matrix & Functional Support

| Functional Area | Available Endpoints | Request Schema | Response Schema | Frontend Integration Role |
| :--- | :--- | :--- | :--- | :--- |
| **System Health** | `GET /health` | Query: `check_timeout` | `HealthResponse` | Gateway status monitoring, offline/degraded detection |
| **System Info** | `GET /` | None | `RootResponse` | API metadata probe (needs routing adjustment for frontend SPA) |
| **Catalog Search** | `GET /api/products` | Query: `q`, `category`, `brand`, `min_price`, `max_price`, `source`, `page`, `page_size` | `ProductListResponse` | Product Catalogue page with facets, sorting, and pagination |
| **Live Aggregation**| `GET /api/products/search` | Query: `q`, `limit` | `ProductListResponse` | Real-time Channel3 live product search bar |
| **Product Detail** | `GET /api/products/{id}` | Path: `id` | `ProductDetailResponse` | Product Details modal/view, competing offers breakdown |
| **Comparison** | `GET /api/products/compare` | Query: `ids` (list or comma-separated) | `ProductComparisonResponse` | Multi-product comparison matrix table |
| **Mandate Create** | `POST /api/mandates` | Body: `SpendingMandateCreate` | `SpendingMandateResponse` | Spending Mandates setup modal/form |
| **Mandate Get** | `GET /api/mandates/{session_id}` | Path: `session_id` | `SpendingMandateResponse` | Active budget indicator, dashboard budget gauge |
| **Mandate Update** | `PUT /api/mandates/{session_id}` | Body: `SpendingMandateUpdate` | `SpendingMandateResponse` | Budget ceiling adjustments |
| **Policy Validation**| `POST /api/mandates/{session_id}/validate` | Body: `PurchaseEvaluationRequest` | `PurchaseEvaluationResponse` | Pre-checkout policy check, mandate compliance banner |
| **AI Assistant** | `POST /api/assistant/query` | Body: `AssistantQueryRequest` | `AssistantQueryResponse` | AI Copilot conversational UI, recommendation cards |
| **Checkout Create** | `POST /api/checkout/orders` | Body: `CheckoutOrderCreate` | `PaymentOrderResponse` or `RetailerRedirectResponse` | Initiates PayPal Sandbox order or redirects to external merchant |
| **Checkout Capture**| `POST /api/checkout/orders/{id}/capture` | Query: `session_id` | `PaymentOrderResponse` | Authoritative backend capture & settlement verification |
| **Order Status** | `GET /api/checkout/orders/{id}` | Query: `session_id` | `PaymentOrderResponse` | Order details modal, capture confirmation |
| **Payment History** | `GET /api/checkout/history/{session_id}` | Path: `session_id`, Query: `page`, `page_size` | `PaymentOrderListResponse` | My Purchases page, Dashboard recent transactions |

---

## 4. Key Architectural & Security Invariants

### 4.1 "AI Suggests. Backend Validates. User Approves. PayPal Processes."
The UI must strictly visualize and honor this boundary:
1. **AI Suggests:** Gemini extracts shopping intent, recommends products, and highlights trade-offs. Gemini *never* approves purchases, modifies budgets, or creates payment orders.
2. **Backend Validates:** The deterministic `SpendingPolicyEngine` evaluates the transaction against the active `SpendingMandate`. It yields `ALLOWED` or `BLOCKED` with explicit reasons. The backend also validates product availability, currency compatibility, and stock freshness.
3. **User Approves:** The user explicitly reviews the itemized breakdown, currency, and total amount, acknowledging that internal orders are simulated sandbox orders.
4. **PayPal Processes:** Payment authorization occurs via PayPal Orders v2 Sandbox. Settlement is authoritatively verified by the backend before status moves to `COMPLETED`.

### 4.2 Dual Purchase Track Distinction
- **Track A (Synthetic Demo Items):** `Product.is_synthetic == True` and `Product.provider == "synthetic"`. Fulfillable via the internal PayPal Sandbox checkout pipeline.
- **Track B (Live Channel3 Marketplace Items):** `Product.is_synthetic == False` or `Product.provider == "channel3"`. Cannot be fulfilled internally. When submitted to `POST /api/checkout/orders`, the backend returns HTTP 400 with a structured `ExternalRetailerCheckoutError`:
  ```json
  {
    "requires_external_checkout": true,
    "retailer_name": "Walmart",
    "product_name": "Garmin Forerunner 265",
    "product_url": "https://walmart.com/ip/...",
    "price": "449.99",
    "currency": "USD"
  }
  ```
  The UI must display this structured redirection dialog and open the merchant's external checkout URL, never claiming an internal payment took place.

### 4.3 Currency Safety & Cross-Currency Invariants
- Numeric prices in disparate currencies (e.g., USD vs INR) are **never** directly compared or converted without a verified FX rate service.
- If a user's mandate is in `INR` (e.g., ₹70,000) and a product's offer is in `USD` ($799.00), the backend classifies the item as `CURRENCY_MISMATCH`. The UI must highlight this with a amber badge and explain that direct numerical budget comparison cannot be established.
- Supported PayPal Sandbox currencies: `USD`, `EUR`, `GBP`, `CAD`, `AUD`, `JPY`, `INR`, `CHF`, `SGD`, `NZD`, `HKD`, `SEK`, `DKK`, `PLN`, `NOK`, `CZK`, `HUF`, `ILS`, `MXN`, `BRL`, `MYR`, `PHP`, `TWD`, `THB`.

### 4.4 Financial Verification & Idempotency
- **No Client-Calculated Totals:** The frontend submits item IDs, offer IDs, and quantities. The backend re-derives unit prices and subtotals directly from the database snapshot.
- **Stable Request IDs:** Order creation uses `paypal_request_id`; order capture uses `paypal_capture_request_id`. Retrying a network timeout does not create duplicate orders or captures.
- **Verified Settlement Requirement:** `PaymentOrder.status` can transition to `COMPLETED` *only* if an authoritative `PaymentCapture` record with `is_verified == True`, matching amount, and matching currency is returned by PayPal.

---

## 5. Gap Analysis: Frontend Requirements vs Backend Support

### 5.1 Fully Supported Features (Zero Backend Changes Needed)
1. **AI Shopping Assistant:** Conversational UI, structured intent rendering, qualification badges (`QUALIFIED`, `CURRENCY_MISMATCH`, `UNVERIFIED_SPECS`, `EXCLUDED`), AI intelligence cards (strengths, weaknesses, trade-offs), and degraded fallback alert.
2. **Product Catalogue & Discovery:** Keyword search, category filters, brand filters, price range filters, data-source tags (`Live Retailer` vs `Demo Catalog`), pagination, and product detail modals.
3. **Price & Specification Comparison:** Multi-product side-by-side matrix, retailer offer spreads, lowest-price retailer identification, and missing spec handling.
4. **Spending Mandates:** Create, view, update budget ceilings, and test candidate purchases against deterministic policy rules.
5. **Checkout & Payment:** Pre-checkout validation, mandate compliance check, PayPal Sandbox popup/redirect flow, capture execution, and receipt display.
6. **External Retailer Checkout:** Modal showing external retailer link, merchant name, and explanation.
7. **Purchase History:** Chronological list of user orders, status badges (`COMPLETED`, `CREATED`, `FAILED`), and receipt inspection.

### 5.2 Features Requiring Client-Side Derivation or Clear Framing
1. **Dashboard KPI Metrics:**
   - *Total Purchases:* Count of orders where `status == "COMPLETED"` from `GET /api/checkout/history/{session_id}`.
   - *Total Spending:* Sum of `total_amount` for `status == "COMPLETED"` orders.
   - *Money Saved:* The backend `RetailerOffer.compare_at_price` represents list prices. If a completed order contains offers with `compare_at_price > price`, savings can be computed from the difference. If no reference price exists, savings must display an honest empty/neutral state (`$0.00` or `N/A`) rather than a fabricated number.
   - *Active Budget:* Derived from `GET /api/mandates/{session_id}` (`total_budget` minus `Total Spending`).
2. **Category-Wise Spending Charts:**
   - Computed client-side by aggregating `OrderItem.subtotal` by category across completed orders retrieved via `GET /api/checkout/history/{session_id}` and `GET /api/checkout/orders/{id}`.
   - If no completed orders exist, display an attractive empty state ("No purchase data yet. Complete your first order to view analytics.").
3. **Session Management (Guest Sessions):**
   - The platform uses guest sessions (`ShoppingSession`). No user authentication/registration endpoint exists in the backend.
   - *Frontend Implementation:* The frontend generates and persists a unique `session_identifier` (e.g., `guest_uuid`) in `localStorage` on first visit. This `session_identifier` is supplied in all mandate and checkout requests, automatically binding mandates and orders to that guest user.

### 5.3 Static File Serving & Root Path Conflict
- **Current State:** In `backend/app/main.py`, `app.include_router(health_router)` registers `GET /` which returns `RootResponse` (JSON).
- **Requirement:** The frontend SPA needs `GET /` to serve `frontend/index.html`, and `/css/*`, `/js/*`, `/assets/*` to serve static files.
- **Proposed Solution (Phase 2):**
  Mount FastAPI `StaticFiles` at `/static` (or directly serve `frontend/`), and route `GET /` to `FileResponse("frontend/index.html")`. Relocate or preserve root API info at `GET /api` or `GET /health` without affecting any `/api/*` endpoints.

---

## 6. Security & Risk Assessment

1. **Credential Exposure Protection:**
   - Client applications never touch PayPal Client Secret or OAuth Bearer Tokens.
   - The frontend communicates strictly with `/api/checkout/*`. All PayPal API calls remain encapsulated within the backend server.
2. **Financial Data Integrity:**
   - Frontend cannot modify `status` to `COMPLETED`. Only a verified backend capture callback transitions state.
   - Client-side currency conversion is prohibited. Disparate currencies must be visually separated.
3. **Deterministic Policy Boundary:**
   - The frontend must never bypass `POST /api/mandates/{session_id}/validate`. The checkout endpoint independently re-runs `SpendingPolicyEngine.evaluate(...)` on order creation regardless of prior UI checks.

---

## 7. Audit Conclusion & Phase 1 Sign-Off

The backend repository is robust, fully tested, and entirely ready to support the BUYWISE AI frontend. All core shopping, comparison, mandate, AI, and payment operations have existing authoritative endpoints.

**Status:** Phase 1 (Audit) complete. Source code unmodified. Awaiting approval to proceed to Phase 2 (Design System & Application Shell).
