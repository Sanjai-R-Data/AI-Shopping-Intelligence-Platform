# RESTful API Specification
## AI-Powered Multilingual Shopping Intelligence Platform

> **Version:** 1.5.0 (API v1 - PayPal Reliability & Final Architecture Approval Pass)  
> **Protocol:** HTTPS / JSON REST  
> **Base Path:** `/api/v1`  
> **Standards:** OpenAPI 3.1, RFC 9457 (Problem Details for HTTP APIs - `application/problem+json`), RFC 8785 (JSON Canonicalization Scheme)  
> **Database Authority:** Entity and attribute names strictly aligned with `DATABASE_DESIGN.md`.

---

## 1. Global API Conventions

### 1.1 Headers, Authentication & CSRF
- `Content-Type: application/json`
- `Accept: application/json, application/problem+json`
- `Accept-Language: en | de | it | es` (Determines AI response and error message locale)
- **Browser Authentication:** Strictly managed via `Secure`, `HttpOnly`, `SameSite=Lax` session cookies. **Session tokens are never exposed to client-side JavaScript or stored in `localStorage`.**
- **CSRF Defense:** State-mutating endpoints (`POST`, `PUT`, `DELETE`) require the `X-CSRF-Token` header, validated against a cryptographic anti-CSRF token issued via `GET /api/v1/auth/csrf-token` or cookie double-submit.
- **Operation-Specific Idempotency:** Mutating operations require `Idempotency-Key: <uuid>`. Keys are strictly scoped by `(user_id, operation, idempotency_key)` in `idempotency_records`.
  - Defined Operations: `ORDER_CREATE`, `ORDER_CAPTURE`, `ORDER_CANCEL`, `ORDER_RECONCILE`.
  - Concurrent duplicate in-flight requests return `409 Conflict` (`IDEMPOTENCY_CONCURRENT_REQUEST`).
  - Key reuse with a mismatched request payload hash returns `409 Conflict` (`IDEMPOTENCY_PAYLOAD_MISMATCH`).
  - Key reuse with an identical payload returns the cached response once resolved.
  - **Active Recovery Protocol (Financial Safety):** Operations remaining `IN_PROGRESS` past 5 minutes trigger an active recovery check, **never automatic failure**. A dedicated worker acquires a row lock (`RECOVERY_IN_PROGRESS`), inspects internal state, and retries PayPal order creation using the stored `paypal_request_id` within the configured retention window (`PAYPAL_IDEMPOTENCY_RETENTION_HOURS = 6` default; up to 72h only if contractually confirmed with a PayPal Account Manager) or queries order status by ID. Mandate reservations are **never released on worker timeout**.
  - **Three Distinct Time Windows:**
    1. `PayPal-Request-Id` Retention: Default 6 hours (configurable via `PAYPAL_IDEMPOTENCY_RETENTION_HOURS`). Creation retry with identical request ID and payload hash is valid solely within this window. Once expired, ambiguous orders escalate to webhook queries or `MANUAL_INTERVENTION_REQUIRED`.
    2. PayPal Order Approval Validity: Up to 3 hours gateway-side buyer approval validity.
    3. Internal Order Expiry (`expires_at`): 15-minute TTL applying to `PENDING_APPROVAL` and `APPROVED` orders prior to capture (strictly excluded while `CREATING` or `CAPTURING`). Stored and compared as canonical 32-character ISO-8601 UTC strings (`YYYY-MM-DDTHH:MM:SS.ffffff+00:00`) via `AwareDateTime`.
  - **In-Flight Order Creation Race Protection:** In the initial local DB transaction, the order is created as `DRAFT`, mandate reservation as `PENDING`, idempotency record as `IN_PROGRESS`, and atomically transitioned to `CREATING` before commit. Cancellation and Expiry are strictly blocked when status is `CREATING` or `CAPTURING`, preventing race-condition fund releases while an external payment operation is in-flight.
  - **Retention & Non-Purge Rule:** Records associated with unsettled payment orders (`DRAFT`, `CREATING`, `PENDING_APPROVAL`, `APPROVED`, `CAPTURING`, `REQUIRES_RECONCILIATION`, `MANUAL_INTERVENTION_REQUIRED`) are **never purged**, regardless of age.

### 1.2 Exact Financial Precision, FX Construction & Monetary Semantics
- **Integer Minor Units:** All monetary values are expressed as 64-bit integer minor units (`*_minor`: paise, cents, pence). Floating-point currency values are never transmitted.
- **Exact Scaled FX Construction via Python `Decimal`:**
  - Upstream provider rate strings are parsed using Python `Decimal` and quantized to a fixed $10^8$ scale factor:
    $$\text{rate\_scaled} = \text{int}\left((\text{Decimal}(rate\_str) \times 10^8).\text{quantize}(\text{Decimal}(1),\; \text{rounding}=\text{ROUND\_HALF\_UP})\right)$$
  - **Same-Currency Invariant:** When `base_currency == quote_currency`, identity conversion is exact: `rate_scaled = 100_000_000`, `scale_factor = 100_000_000`, `exchange_rate_id = NULL`.
  - **Cross-Currency Invariant:** When `base_currency <> quote_currency`, an authentic timestamped `exchange_rates` record is **mandatory** with composite foreign-key constraint `fk_reservations_exchange_rate_composite` referencing `uq_rates_composite` under `ON DELETE RESTRICT`. No unsafe defaults on `applied_rate_scaled`; no identity-rate fallback permitted. Mandatory transactional validation asserts matching currency pair, rate, and timestamp.
  - **Mandate & FX Quote Currency Invariant:** Database constraint `chk_mandate_currency_match` strictly guarantees that the mandate base currency matches the destination quote currency of the applied rate (`CHECK (currency = quote_currency)`). In addition, constraint `chk_fx_currency_consistency` enforces strict same-currency vs cross-currency invariants.
  - **Stale-Rate Policy:** Maximum rate age is 24 hours in dev, 1 hour in prod. Missing or stale rates reject checkout with an RFC 9457 error.
- **Unambiguous Currency Association:** **Every monetary amount field in every request and response is strictly paired with an unambiguous ISO 4217 currency identifier.** Amounts across differing currencies (e.g., PayPal USD settlement vs. user mandate INR consumption) are explicitly segregated into distinct semantic objects.
- **Locked Exchange Rate & FX Buffer Policy:**
  - The exchange rate is locked for the order's 15-minute validity window (`expires_at`).
  - The FX buffer (e.g., 200 bps = 2.0%) is reserved for volatility protection but **never counted as expenditure**.
  - Upon capture, actual purchase expenditure is finalized at the locked rate, and **the excess FX buffer is immediately released back to the user's available budget.**
- **Data Provenance:** All products and offers carry `data_provenance: "LIVE_PROVIDER_DATA" | "SYNTHETIC_DEMO_DATA"`.

### 1.3 Standard Error Response Schema (RFC 9457)
Errors return `Content-Type: application/problem+json`:
```json
{
  "type": "https://api.shoppingsense.ai/errors/policy-violation",
  "title": "Spending Policy Violation",
  "status": 422,
  "detail": "Purchase price of ₹17,034 INR (inclusive of FX buffer) exceeds active mandate per-item limit of ₹15,000 INR.",
  "instance": "/api/v1/checkout/orders",
  "code": "MANDATE_ITEM_PRICE_EXCEEDED",
  "timestamp": "2026-11-01T22:50:00Z",
  "invalid_params": [
    {
      "name": "item_price_minor",
      "currency": "INR",
      "reason": "Exceeds max allowed 1500000 minor units"
    }
  ]
}
```

---

## 2. Authentication & Identity Management (`/api/v1/auth`)

### 2.1 Fetch Anti-CSRF Token
- **Endpoint:** `GET /api/v1/auth/csrf-token`
- **Auth:** Optional
- **Response `200 OK`:**
```json
{
  "csrf_token": "csrf_99a81bc20412e8"
}
```

### 2.2 Create Ephemeral Guest Session
- **Endpoint:** `POST /api/v1/auth/guest-session`
- **Auth:** None (Header: `X-CSRF-Token`)
- **Response Headers:** `Set-Cookie: session_token=gst_sess_9f83b2...; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=604800`
- **Response `201 Created`:**
```json
{
  "user_id": "usr_guest_88192a",
  "is_guest": true,
  "preferred_currency": "USD",
  "preferred_language": "en",
  "expires_at": "2026-11-08T22:50:00Z"
}
```

### 2.3 Register User & Migrate Guest Data
- **Endpoint:** `POST /api/v1/auth/register`
- **Auth:** Optional Guest Cookie (Header: `X-CSRF-Token`)
- **Request Body:**
```json
{
  "email": "sarah.connor@example.com",
  "password": "SecurePassword123!",
  "preferred_language": "de",
  "preferred_currency": "EUR"
}
```
- **Response Headers:** `Set-Cookie: session_token=auth_sess_109bf8...; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=2592000`
- **Response `201 Created`:**
```json
{
  "user_id": "usr_e03b4129-9c2b-4b2a-88fa-91b790d8102a",
  "email": "sarah.connor@example.com",
  "migrated_items_count": 3,
  "created_at": "2026-11-01T22:50:00Z"
}
```

### 2.4 User Login
- **Endpoint:** `POST /api/v1/auth/login`
- **Auth:** None (Header: `X-CSRF-Token`)
- **Request Body:**
```json
{
  "email": "sarah.connor@example.com",
  "password": "SecurePassword123!"
}
```
- **Response Headers:** `Set-Cookie: session_token=auth_sess_109bf8...; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=2592000`
- **Response `200 OK`:**
```json
{
  "user": {
    "id": "usr_e03b4129-9c2b-4b2a-88fa-91b790d8102a",
    "email": "sarah.connor@example.com",
    "display_name": "Sarah Connor",
    "preferred_language": "de",
    "preferred_currency": "EUR"
  }
}
```

---

## 3. Product Discovery & Aggregation (`/api/v1/products`)

### 3.1 Search & Filter Products
- **Endpoint:** `GET /api/v1/products/search`
- **Query Parameters:**
  - `query` (string, required): e.g., `"noise cancelling headphones"`
  - `category` (string, optional): e.g., `"audio/headphones"`
  - `min_price_minor` (int, optional): e.g., `500000`
  - `max_price_minor` (int, optional): e.g., `3500000`
  - `currency` (string, optional, default: `"USD"`): `USD | EUR | GBP | INR`
  - `page` (int, default: 1), `limit` (int, default: 20)
- **Response `200 OK`:**
```json
{
  "total": 1,
  "page": 1,
  "limit": 20,
  "target_currency": "INR",
  "products": [
    {
      "id": "prod_sony_wh1000xm5",
      "canonical_slug": "sony-wh-1000xm5-wireless-headphones",
      "title": "Sony WH-1000XM5 Wireless Headphones",
      "brand": "Sony",
      "category": "audio/headphones",
      "data_provenance": "LIVE_PROVIDER_DATA",
      "provider_source": "CHANNEL3",
      "primary_image_url": "https://images.example.com/sony-xm5.jpg",
      "original_pricing": {
        "min_price_minor": 32800,
        "max_price_minor": 39999,
        "currency": "USD"
      },
      "estimated_pricing": {
        "min_price_minor": 2738800,
        "max_price_minor": 3339900,
        "currency": "INR",
        "is_estimated_conversion": true,
        "applied_rate_scaled": 8350000000,
        "conversion_rate_timestamp": "2026-11-01T22:00:00Z"
      },
      "retailer_count": 3,
      "vfm_score": 88.5,
      "primary_specs": {
        "battery_life": "30 hours",
        "weight": "250g"
      },
      "eligible_for_sandbox": true
    }
  ]
}
```

### 3.2 Get Product Details & Offers
- **Endpoint:** `GET /api/v1/products/{product_id}`
- **Response `200 OK`:**
```json
{
  "id": "prod_sony_wh1000xm5",
  "title": "Sony WH-1000XM5 Wireless Headphones",
  "brand": "Sony",
  "category": "audio/headphones",
  "data_provenance": "LIVE_PROVIDER_DATA",
  "specifications": [
    {"group": "Battery", "name": "Battery Life", "value": "30", "unit": "hours"}
  ],
  "offers": [
    {
      "id": "off_bestbuy_01",
      "retailer_name": "Best Buy",
      "offer_type": "ELIGIBLE_SANDBOX",
      "original_price": {
        "amount_minor": 32800,
        "currency": "USD"
      },
      "estimated_converted_price": {
        "amount_minor": 2738800,
        "currency": "INR",
        "is_estimated_conversion": true,
        "applied_rate_scaled": 8350000000
      },
      "in_stock": true,
      "data_provenance": "LIVE_PROVIDER_DATA",
      "provider_source": "CHANNEL3"
    }
  ]
}
```

### 3.3 Genuine Price History
- **Endpoint:** `GET /api/v1/products/{product_id}/price-history`
- **Response `200 OK`:**
```json
{
  "product_id": "prod_sony_wh1000xm5",
  "currency": "USD",
  "data_provenance": "LIVE_PROVIDER_DATA",
  "has_historical_data": true,
  "snapshots": [
    {"recorded_at": "2026-10-01T00:00:00Z", "lowest_price_minor": 39999, "average_price_minor": 39999, "currency": "USD"},
    {"recorded_at": "2026-10-15T00:00:00Z", "lowest_price_minor": 34999, "average_price_minor": 37900, "currency": "USD"},
    {"recorded_at": "2026-11-01T00:00:00Z", "lowest_price_minor": 32800, "average_price_minor": 34550, "currency": "USD"}
  ],
  "all_time_low_minor": 32800,
  "all_time_high_minor": 39999,
  "price_currency": "USD"
}
```

---

## 4. Product Intelligence & Comparison (`/api/v1/intelligence`)

### 4.1 Multi-Product Specification & Price Comparison
- **Endpoint:** `POST /api/v1/intelligence/compare`
- **Request Body:**
```json
{
  "product_ids": [
    "prod_sony_wh1000xm5",
    "prod_bose_qc45"
  ],
  "target_currency": "INR"
}
```
- **Response `200 OK`:**
```json
{
  "compared_products": [
    {
      "id": "prod_sony_wh1000xm5",
      "title": "Sony WH-1000XM5",
      "data_provenance": "LIVE_PROVIDER_DATA",
      "original_pricing": {
        "lowest_price_minor": 32800,
        "currency": "USD"
      },
      "estimated_pricing": {
        "lowest_price_minor": 2738800,
        "currency": "INR"
      },
      "vfm_score": 88.5,
      "key_advantages": ["Longer battery life (30h vs 24h)"],
      "trade_offs": ["Non-folding headband"]
    },
    {
      "id": "prod_bose_qc45",
      "title": "Bose QuietComfort 45",
      "data_provenance": "LIVE_PROVIDER_DATA",
      "original_pricing": {
        "lowest_price_minor": 27900,
        "currency": "USD"
      },
      "estimated_pricing": {
        "lowest_price_minor": 2329650,
        "currency": "INR"
      },
      "vfm_score": 86.0,
      "key_advantages": ["₹4,091 cheaper", "Folding design"],
      "trade_offs": ["6h less battery life"]
    }
  ],
  "price_delta": {
    "absolute_difference_minor": 409150,
    "delta_currency": "INR",
    "cheaper_product_id": "prod_bose_qc45",
    "percentage_saving": 14.9
  }
}
```

---

## 5. Multilingual AI Shopping Assistant (`/api/v1/ai`)

### 5.1 Chat Turn with Shopping Copilot
- **Endpoint:** `POST /api/v1/ai/chat`
- **Auth:** Required via HttpOnly Cookie (Header: `X-CSRF-Token`)
- **Request Body:**
```json
{
  "message": "¿Cuál de estos auriculares ofrece mejor relación calidad-precio y cabe en mi presupuesto de 25000 INR?",
  "conversation_id": "cnv_7721ab",
  "language": "es",
  "active_product_context_ids": ["prod_sony_wh1000xm5", "prod_bose_qc45"]
}
```
- **Response `200 OK`:**
```json
{
  "conversation_id": "cnv_7721ab",
  "language": "es",
  "assistant_response": "Para un presupuesto máximo de ₹25,000 INR, el **Bose QuietComfort 45** es la opción recomendada a un precio estimado de **₹23,296 INR**, cumpliendo estrictamente con tu presupuesto. El Sony WH-1000XM5 cuesta aproximadamente ₹27,388 INR y excede tu límite.",
  "recommended_products": [
    {
      "id": "prod_bose_qc45",
      "title": "Bose QuietComfort 45",
      "estimated_price_minor": 2329650,
      "currency": "INR",
      "fit_status": "WITHIN_BUDGET"
    }
  ],
  "mandate_evaluation": {
    "has_active_mandate": true,
    "budget_ceiling_minor": 2500000,
    "mandate_currency": "INR",
    "is_compliant": true
  }
}
```

---

## 6. Deterministic Spending Mandates (`/api/v1/mandates`)

### 6.1 Create or Update Spending Mandate
- **Endpoint:** `POST /api/v1/mandates`
- **Auth:** Required (HttpOnly Cookie, Header: `X-CSRF-Token`)
- **Request Body:**
```json
{
  "mandate_name": "Q4 Audio Cap",
  "max_budget_minor": 5000000,
  "currency": "INR",
  "max_price_per_item_minor": 3000000,
  "max_quantity_per_order": 2,
  "allowed_categories": ["audio/headphones"],
  "expiry_date": "2026-12-31T23:59:59Z"
}
```
- **Response `201 Created`:**
```json
{
  "mandate_id": "mand_4091ab7",
  "mandate_name": "Q4 Audio Cap",
  "budget_summary": {
    "max_budget_minor": 5000000,
    "reserved_amount_minor": 0,
    "consumed_amount_minor": 0,
    "remaining_budget_minor": 5000000,
    "currency": "INR"
  },
  "is_active": true
}
```

### 6.2 Get Active Mandate Summary
- **Endpoint:** `GET /api/v1/mandates/active`
- **Response `200 OK`:**
```json
{
  "mandate_id": "mand_4091ab7",
  "mandate_currency": "INR",
  "max_budget_minor": 5000000,
  "reserved_amount_minor": 0,
  "consumed_amount_minor": 2329650,
  "remaining_budget_minor": 2670350,
  "utilization_percentage": 46.6,
  "status": "HEALTHY"
}
```

---

## 7. Decoupled Checkout & PayPal Sandbox Processing (`/api/v1/checkout`)

### 7.1 Create Sandbox Order (Dual Mode: Mandate-Backed vs No-Mandate)
- **Endpoint:** `POST /api/v1/checkout/orders`
- **Headers:** `Idempotency-Key: <uuid>`, `X-CSRF-Token: <token>`
- **Operation:** `ORDER_CREATE`
- **Internal Handling:** Generates and stores a unique UUID v4 `paypal_request_id` on the order record and transmits it via `PayPal-Request-Id: <uuid>` to PayPal Orders v2 API. Synchronizes `expires_at` to exactly 15 minutes.
  - **Authoritative 8-Step Order Creation Sequence:**
    1. Begin short-lived local DB transaction: generate order identifiers, UUID v4 `paypal_request_id`, and synchronized 15-minute `expires_at`.
    2. Insert `payment_orders` with initial status `DRAFT`.
    3. If mandate-backed, insert `mandate_reservations` with status `PENDING` (locking budget and FX buffer, enforcing `chk_mandate_currency_match` and `chk_fx_currency_consistency`).
    4. Insert `idempotency_records` with status `IN_PROGRESS`.
    5. Atomically transition `payment_orders` from `DRAFT` to `CREATING` (`WHERE id = :order_id AND status = 'DRAFT'`).
    6. Commit local DB transaction and release database connection back to the pool before any external network request (in-flight `CREATING` state strictly blocks concurrent cancellation and expiry).
    7. Dispatch PayPal Sandbox `POST /v2/checkout/orders` request with header `PayPal-Request-Id: <paypal_request_id>`.
    8. In a new short-lived DB transaction, persist returned `paypal_order_id`, transition `CREATING` to `PENDING_APPROVAL`, complete idempotency record, and commit.
  - **Alternative Outcome Branches from Step 7:**
    - *Branch 7a (Happy Path -> Step 8):* PayPal responds 201 Created with `paypal_order_id`. Proceed directly to Step 8.
    - *Branch 7b (Definitive Failure Compensation):* On PayPal validation rejection (HTTP 400, 422, 401, 403), transition order from `CREATING` to `FAILED`, release mandate reservation (`status = 'RELEASED'`), mark idempotency `FAILED`, and return RFC 9457 error.
    - *Branch 7c (Ambiguous Outcome / Network Timeout):* On gateway timeout (HTTP 504), socket drop, 5xx server error, or local DB persistence failure, **mandate reservation remains strictly locked**. Transition order from `CREATING` to `REQUIRES_RECONCILIATION`. Return HTTP 202 Accepted standard JSON operation-status response (NOT RFC 9457 error).
    - *Branch 7d (Active Reconciliation Retry):* Background reconciler retries creation using stored `PayPal-Request-Id` within the default 6-hour window. Mandate funds are never released prematurely.

#### Request Payload A (Mandate-Backed):
```json
{
  "retailer_offer_id": "off_bestbuy_01",
  "quantity": 1,
  "mandate_id": "mand_4091ab7"
}
```
- **Response `201 Created` (Mandate-Backed):**
```json
{
  "internal_order_id": "ord_88201a",
  "internal_order_number": "ORD-20261101-9921",
  "status": "PENDING_APPROVAL",
  "mandate_applied": true,
  "order_pricing": {
    "total_amount_minor": 32800,
    "currency": "USD"
  },
  "paypal_order": {
    "paypal_order_id": "5O190127TN364715T"
  },
  "mandate_reservation": {
    "mandate_id": "mand_4091ab7",
    "mandate_currency": "INR",
    "applied_exchange_rate_scaled": 8350000000,
    "estimated_converted_price_minor": 2738800,
    "fx_buffer_minor": 54776,
    "total_reserved_minor": 2793576,
    "remaining_unreserved_budget_minor": 2206424
  },
  "expires_at": "2026-11-01T23:05:00Z",
  "simulation_disclaimer": "PayPal Sandbox Demonstration Order. No physical goods will be shipped."
}
```

#### Request Payload B (No-Mandate Checkout under Baseline Safeguards):
```json
{
  "retailer_offer_id": "off_bestbuy_01",
  "quantity": 1,
  "mandate_id": null,
  "user_confirmation": {
    "acknowledge_no_mandate": true
  }
}
```
- **Response `201 Created` (No-Mandate):**
```json
{
  "internal_order_id": "ord_88202b",
  "internal_order_number": "ORD-20261101-9922",
  "status": "PENDING_APPROVAL",
  "mandate_applied": false,
  "order_pricing": {
    "total_amount_minor": 32800,
    "currency": "USD"
  },
  "paypal_order": {
    "paypal_order_id": "5O190127TN364716U"
  },
  "mandate_reservation": null,
  "baseline_safeguards": {
    "max_order_quantity_limit": 5,
    "canonical_ceiling_amount_minor": 100000,
    "canonical_ceiling_currency": "USD",
    "order_converted_to_ceiling_minor": 32800,
    "safeguard_status": "COMPLIANT"
  },
  "expires_at": "2026-11-01T23:05:00Z",
  "simulation_disclaimer": "PayPal Sandbox Demonstration Order. No physical goods will be shipped."
}
```

---

### 7.2 Authoritative PayPal Capture (Persisted State Machine & One-Capture Invariant)
- **Endpoint:** `POST /api/v1/checkout/orders/{internal_order_id}/capture`
- **Headers:** `Idempotency-Key: <uuid>`, `X-CSRF-Token: <token>`
- **Operation:** `ORDER_CAPTURE`
- **Strict Invariant:** Client-side PayPal JavaScript SDK capture (`actions.order.capture()`) is **strictly prohibited**. The backend exclusively owns capture.
- **Persisted State Sequence:**
  1. Server fetches internal order, retrieves `stored_paypal_order_id`. Rejects with `409 Conflict` if internal order status is already `CANCELLED`, `EXPIRED`, or `COMPLETED`.
  2. Queries PayPal `GET /v2/checkout/orders/{stored_paypal_order_id}` to verify buyer approval (`status == 'APPROVED'`).
  3. **Atomically persists state to `APPROVED`**: `UPDATE payment_orders SET status = 'APPROVED', updated_at = :now WHERE id = :id AND status = 'PENDING_APPROVAL'`.
  4. **Enforces One-Capture-Per-Order Invariant**: Atomically transitions from `APPROVED` to `CAPTURING` under row lock (`UPDATE payment_orders SET status = 'CAPTURING', updated_at = :now WHERE id = :id AND status = 'APPROVED'`). Any concurrent capture, cancellation, or expiry call receives `409 Conflict`.
  5. Executes capture with PayPal (`POST /v2/checkout/orders/{stored_paypal_order_id}/capture`).
  6. On success: transitions order to `COMPLETED`, commits reservation to `COMMITTED`, and releases excess FX buffer.
  7. On ambiguous gateway response: transitions order to `REQUIRES_RECONCILIATION`. Funds remain locked.

#### Response `200 OK` (Mandate-Backed Capture with Buffer Release):
```json
{
  "internal_order_id": "ord_88201a",
  "internal_order_number": "ORD-20261101-9921",
  "status": "COMPLETED",
  "mandate_applied": true,
  "payment_settlement": {
    "amount_captured_minor": 32800,
    "currency": "USD",
    "paypal_capture_id": "789012345678",
    "captured_at": "2026-11-01T22:50:00Z"
  },
  "mandate_settlement": {
    "mandate_id": "mand_4091ab7",
    "mandate_currency": "INR",
    "applied_exchange_rate_scaled": 8350000000,
    "consumed_amount_minor": 2738800,
    "released_fx_buffer_minor": 54776,
    "remaining_budget_minor": 2261200
  },
  "receipt": {
    "order_number": "ORD-20261101-9921",
    "is_demonstration_order": true,
    "fulfillment_notice": "Simulated order fulfilled in Sandbox mode."
  }
}
```

#### Response `200 OK` (No-Mandate Capture):
```json
{
  "internal_order_id": "ord_88202b",
  "internal_order_number": "ORD-20261101-9922",
  "status": "COMPLETED",
  "mandate_applied": false,
  "payment_settlement": {
    "amount_captured_minor": 32800,
    "currency": "USD",
    "paypal_capture_id": "789012345679",
    "captured_at": "2026-11-01T22:50:00Z"
  },
  "mandate_settlement": null,
  "receipt": {
    "order_number": "ORD-20261101-9922",
    "is_demonstration_order": true,
    "fulfillment_notice": "Simulated order fulfilled in Sandbox mode."
  }
}
```

#### Response `202 Accepted` (Timeout / Ambiguous Gateway Response - Standard JSON Operation Status):
*Note: A 202 Accepted indicates an accepted asynchronous operation awaiting resolution, NOT an error. It is formatted as standard `application/json`.*
```json
{
  "internal_order_id": "ord_88201a",
  "status": "REQUIRES_RECONCILIATION",
  "reconciliation_status": "PENDING_INVESTIGATION",
  "status_url": "/api/v1/checkout/orders/ord_88201a/status",
  "reconciliation_endpoint": "/api/v1/checkout/orders/ord_88201a/reconcile",
  "retry_after_seconds": 30,
  "message": "Payment processing outcome with PayPal is currently ambiguous due to gateway timeout. Mandate reservation remains securely locked while backend automated reconciliation is underway. Please query the status endpoint shortly."
}
```

---

### 7.3 Get Order Status (`/api/v1/checkout/orders/{id}/status`)
- **Endpoint:** `GET /api/v1/checkout/orders/{internal_order_id}/status`
- **Auth:** Required (HttpOnly Cookie)
- **Response `200 OK`:**
```json
{
  "internal_order_id": "ord_88201a",
  "internal_order_number": "ORD-20261101-9921",
  "status": "REQUIRES_RECONCILIATION",
  "reconciliation_status": "IN_PROGRESS",
  "total_amount_minor": 32800,
  "currency": "USD",
  "mandate_applied": true,
  "reservation_locked": true,
  "expires_at": "2026-11-01T23:05:00Z",
  "last_checked_at": "2026-11-01T22:51:30Z"
}
```

---

### 7.4 Order Cancellation (Race-Safe Mandate Reservation Release)
- **Endpoint:** `POST /api/v1/checkout/orders/{internal_order_id}/cancel`
- **Headers:** `Idempotency-Key: <uuid>`, `X-CSRF-Token: <token>`
- **Operation:** `ORDER_CANCEL`
- **Precondition:** Order must be in `PENDING_APPROVAL` or `APPROVED` (buyer approved in PayPal modal but abandoned or chose to cancel in the app prior to backend capture initiation). Returns `409 Conflict` if order is in `CREATING` (`ORDER_CREATION_IN_FLIGHT`), `CAPTURING` (`CAPTURE_IN_PROGRESS`), or is in `COMPLETED`, `CANCELLED`, `EXPIRED`, `REQUIRES_RECONCILIATION`, or `MANUAL_INTERVENTION_REQUIRED`.
- **Atomic Transition:**
  ```sql
  UPDATE payment_orders 
  SET status = 'CANCELLED', updated_at = :now 
  WHERE id = :internal_order_id AND status IN ('PENDING_APPROVAL', 'APPROVED')
  RETURNING id;
  ```
- **Response `200 OK` (Mandate-Backed):**
```json
{
  "internal_order_id": "ord_88201a",
  "status": "CANCELLED",
  "mandate_applied": true,
  "mandate_impact": {
    "mandate_id": "mand_4091ab7",
    "mandate_currency": "INR",
    "released_reserved_minor": 2793576,
    "current_remaining_budget_minor": 5000000
  },
  "message": "Order cancelled successfully. Budget unreserved."
}
```

---

### 7.5 Order Payment Reconciliation
- **Endpoint:** `POST /api/v1/checkout/orders/{internal_order_id}/reconcile`
- **Headers:** `Idempotency-Key: <uuid>`, `X-CSRF-Token: <token>`
- **Operation:** `ORDER_RECONCILE`
- **Internal Handling:** Retries order creation with stored `paypal_request_id` within the configured retention window (`PAYPAL_IDEMPOTENCY_RETENTION_HOURS = 6` default) if missing `paypal_order_id`, or queries PayPal `GET /v2/checkout/orders/{paypal_order_id}` if ID is known. Does NOT call imaginary search endpoints. If retention has expired or retries are exhausted without authoritative resolution, order transitions to `MANUAL_INTERVENTION_REQUIRED`. Mandate funds remain strictly locked.
- **Response `200 OK`:**
```json
{
  "internal_order_id": "ord_88201a",
  "previous_status": "REQUIRES_RECONCILIATION",
  "resolved_status": "COMPLETED",
  "payment_settlement": {
    "amount_captured_minor": 32800,
    "currency": "USD",
    "paypal_capture_id": "789012345678"
  },
  "mandate_settlement": {
    "mandate_id": "mand_4091ab7",
    "mandate_currency": "INR",
    "consumed_amount_minor": 2738800,
    "remaining_budget_minor": 2261200
  },
  "reconciled_at": "2026-11-01T22:52:00Z"
}
```

---

### 7.6 External Retailer Outbound Redirect Link
- **Endpoint:** `GET /api/v1/checkout/retailer-redirect/{offer_id}`
- **Description:** Validates outbound URL against exact approved host whitelist (`https://` required). Logs clickout to `shopping_history`.
- **Response `200 OK`:**
```json
{
  "offer_id": "off_amazon_02",
  "retailer_name": "Amazon",
  "redirect_url": "https://www.amazon.com/dp/B09XS7JWHH?tag=hackathon-partner-20",
  "host_verified": true,
  "disclosure": "You are navigating to an external marketplace. Checkout will occur directly on Amazon."
}
```

---

### 7.7 PayPal Webhook Ingestion (`/api/v1/payments/webhooks`)
- **Endpoint:** `POST /api/v1/payments/webhooks`
- **Auth:** Public endpoint with mandatory cryptographic PayPal signature verification
- **Verification Headers:** `paypal-auth-algo`, `paypal-cert-url`, `paypal-transmission-id`, `paypal-transmission-sig`, `paypal-transmission-time`
- **Recoverable Webhook Lifecycle (3 Phases / Canonical 9-Step Processing Sequence):**
  1. Validates webhook signature using PayPal signature verification (`POST /v1/notifications/verify-webhook-signature`). Rejects unverified deliveries immediately with `401 Unauthorized`.
  2. Durably persists delivery into `paypal_webhook_events` with initial status `RECEIVED` (`UNIQUE (paypal_event_id)`). Replays return `200 OK` without duplicate processing.
  3. Returns `200 OK` to PayPal immediately **after durable persistence** of `RECEIVED`.
  4. **Phase 1 — Atomic Lease Claim (Steps 1–2):**
     - **Step 1 (Claim Eligible Lease):** Recoverable background worker atomically queries and claims an eligible event under row-level lease with fencing:
       ```sql
       UPDATE paypal_webhook_events
       SET status = 'PROCESSING', worker_id = :worker_id, lease_token = :new_token,
           lease_generation = lease_generation + 1, processing_started_at = :now,
           lease_expires_at = :lease_expiry, updated_at = :now
       WHERE id = (
           SELECT id FROM paypal_webhook_events
           WHERE status = 'RECEIVED'
              OR (status = 'RETRYABLE_FAILED' AND next_retry_at IS NOT NULL AND next_retry_at <= :now)
              OR (status = 'PROCESSING' AND lease_expires_at IS NOT NULL AND lease_expires_at <= :now)
           ORDER BY created_at ASC
           LIMIT 1
           FOR UPDATE SKIP LOCKED
       )
       RETURNING id, paypal_event_id, event_type, payload, lease_token, lease_generation;
       ```
     - **Step 2 (Commit Lease Claim & Release DB Connection):** The claim transaction is committed immediately. The database connection is explicitly returned to the pool so that no database resources or connection pool slots are held during external REST communication.
  5. **Phase 2 — External REST Verification Outside DB Transaction (Step 3):**
     - **Step 3 (Execute External REST Verification):** With **zero database connections held**, worker queries authoritative PayPal REST API:
       - `checkout-order` events (`CHECKOUT.ORDER.*`): queries PayPal Orders v2 via `GET /v2/checkout/orders/{paypal_order_id}`.
       - `capture` events (`PAYMENT.CAPTURE.*`): queries PayPal Payments v2 via `GET /v2/payments/captures/{paypal_capture_id}`, extracting parent order ID via `supplementary_data.related_ids.order_id` to correlate to internal payment order. Capture IDs are **never** passed to order endpoints.
       - *Heartbeat Lease Renewal:* If external processing takes longer than 30 seconds, worker executes a brief, isolated heartbeat query to extend `lease_expires_at`:
         ```sql
         UPDATE paypal_webhook_events
         SET lease_expires_at = :new_expiry, updated_at = :now
         WHERE id = :id AND status = 'PROCESSING' AND lease_token = :token AND lease_expires_at > :now;
         ```
         If `result.rowcount != 1`, the worker lost the lease and must abort immediately without mutating application state.
  6. **Phase 3 — Financial Processing Transaction & Atomicity Boundary (Steps 4–9):**
     - **Step 4 (Begin Processing Transaction):** Worker acquires a new database connection and opens an explicit transaction (`async with session.begin():`).
     - **Step 5 (Lock Internal Records & Validate Parent-Order Correlation):**
       - Worker locks the associated `payment_orders` row (`FOR UPDATE`).
       - **Strict Parent-Order Correlation Check:** For capture webhooks, before inserting any capture or mutating order/mandate state, worker verifies that the internal order's `paypal_order_id` matches the verified capture's parent order ID:
         ```python
         verified_parent_order_id = verified_res.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
         if not verified_parent_order_id or internal_payment_order.paypal_order_id != verified_parent_order_id:
             # Escalate: parent order mismatch detected
             internal_payment_order.status = "MANUAL_INTERVENTION_REQUIRED"
             # Append FINANCIAL_DISCREPANCY_DETECTED audit event with reason 'PARENT_ORDER_MISMATCH'
             # Transition webhook to MANUAL_REVIEW_REQUIRED under fenced lease
             # Enforce result.rowcount == 1 (rollback if != 1)
         ```
         If mismatched, the system **never** inserts the capture, **never** debits the mandate, and **never** marks the order `COMPLETED`. This is distinct from a duplicate-capture conflict.
     - **Step 6 (Savepoint-Protected Capture Insertion):**
       - Inside a nested savepoint (`async with session.begin_nested():`), worker attempts to insert the capture into `payment_captures`.
       - If `uq_payment_captures_paypal_capture_id` raises `IntegrityError`, the savepoint safely rolls back without aborting the outer transaction.
     - **Step 7 (Resolve Outcome & Apply Business Logic):**
       - *Active Orders (First-Time Capture):* Validates amount, currency, and capture state. Mutates internal order safely without regressing terminal states (`COMPLETED`, `CANCELLED`, `EXPIRED`, `FAILED`). Debits approved mandate if applicable.
       - *Capture on Terminal Order:* If PayPal confirms capture on an order in `CANCELLED`, `EXPIRED`, or `FAILED`, inserts `payment_captures` with `is_discrepancy = true` and `discrepancy_reason = 'CAPTURE_ON_TERMINAL_ORDER'`, escalates order to `MANUAL_INTERVENTION_REQUIRED`, appends `FINANCIAL_DISCREPANCY_DETECTED` audit event, and marks webhook `PROCESSED`.
       - *Duplicate Capture Handling (Uniform 6-Field Comparison Contract):* If savepoint caught a duplicate, queries existing capture and checks all 6 fields: (1) `paypal_capture_id`, (2) `payment_order_id`, (3) Parent `paypal_order_id`, (4) `amount_captured_minor`, (5) `currency`, (6) `capture_status`.
         - *Identical Duplicate:* Benign replay. No duplicate debit; webhook marked `PROCESSED`.
         - *Conflicting Duplicate:* Attribute mismatch. Order escalates to `MANUAL_INTERVENTION_REQUIRED`, logs `FINANCIAL_DISCREPANCY_DETECTED` (`DUPLICATE_CAPTURE_CONFLICT`), webhook transitions to `MANUAL_REVIEW_REQUIRED`.
     - **Step 8 (Fenced Finalization with Universal Row-Count Verification):**
       - Worker executes the conditional update on `paypal_webhook_events`:
         ```sql
         UPDATE paypal_webhook_events
         SET status = :final_status, processed_at = :now, updated_at = :now,
             lease_token = NULL, lease_expires_at = NULL, last_error = :last_error
         WHERE id = :id AND status = 'PROCESSING' AND lease_token = :token AND lease_expires_at > :now;
         ```
       - **Strict Universal Row-Count Enforcement Rule:** The worker MUST verify `fence_result.rowcount == 1`. If `rowcount == 0` (lease expired or stolen) or `> 1` (multi-row violation), worker executes `await session.rollback()`. A stale worker must NEVER commit order updates, capture records, mandate debits, or audit events.
     - **Step 9 (Atomic Transaction Commit):**
       - When `fence_result.rowcount == 1`, the processing transaction commits all changes atomically: capture record, order status update, mandate debit, audit ledger entries, and webhook status.
  7. **Fenced Failure & Retry Transitions:**
     - On transient network/timeout failure: transitions to `RETRYABLE_FAILED` with exponential backoff (`retry_count += 1`):
       ```sql
       UPDATE paypal_webhook_events
       SET status = 'RETRYABLE_FAILED', retry_count = retry_count + 1, next_retry_at = :next_retry_at,
           last_error = :error_msg, lease_token = NULL, lease_expires_at = NULL, updated_at = :now
       WHERE id = :id AND status = 'PROCESSING' AND lease_token = :token AND lease_expires_at > :now;
       ```
       Enforces `rowcount == 1`; rolls back if fence fails.
     - On unrecoverable error or max retries exceeded: transitions to `MANUAL_REVIEW_REQUIRED`:
       ```sql
       UPDATE paypal_webhook_events
       SET status = 'MANUAL_REVIEW_REQUIRED', last_error = :error_msg,
           lease_token = NULL, lease_expires_at = NULL, updated_at = :now
       WHERE id = :id AND status = 'PROCESSING' AND lease_token = :token AND lease_expires_at > :now;
       ```
       Enforces `rowcount == 1`; rolls back if fence fails.
- **Response `200 OK`:**
```json
{
  "status": "ACCEPTED",
  "event_id": "WH-9876543210ABCDEFG",
  "event_type": "CHECKOUT.ORDER.APPROVED"
}
```
