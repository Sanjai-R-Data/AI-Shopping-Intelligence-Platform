# BUYWISE AI — Frontend to Backend API Mapping Specification

> **System:** BUYWISE AI  
> **Tagline:** Discover smarter. Compare deeper. Spend responsibly.  
> **Milestone:** Phase 1 — Repository and API Audit  
> **Document:** UI API Mapping Specification  
> **Protocol:** REST JSON / RFC 9457 Problem Details (`application/problem+json`)

---

## 1. Overview & Communication Conventions

The BUYWISE AI frontend is a single-page Vanilla JavaScript application that communicates with the backend via same-origin REST requests (`/api/*`).

### Global Conventions
- **Session Identification:** The frontend generates a unique UUID `session_identifier` stored in `localStorage` under `buywise_session_id`. When creating spending mandates or orders, this identifier is sent to bind the guest session. Once resolved, the backend returns the canonical `session_id` (UUID), which is persisted in application state.
- **Error Handling:** Errors return RFC 9457 Problem Details with HTTP 4xx/5xx status codes:
  ```json
  {
    "type": "about:blank",
    "title": "Bad Request",
    "status": 400,
    "detail": "Descriptive message or structured error object",
    "instance": "/api/checkout/orders"
  }
  ```
- **Financial Precision:** All prices in responses are formatted as strings or high-precision floats/decimals with currency codes (ISO-4217).

---

## 2. Page & Component API Mapping

### 2.1 Global Application Shell & Header

| UI Component | Action / Trigger | Backend Endpoint | Method | Parameters / Body | Key Response Fields Used |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **System Status Pill** | On app initialization & periodic check | `/health` | `GET` | `check_timeout=5` | `status` ("healthy", "degraded"), `database` ("connected") |
| **Guest Session Badge** | On app load | `/api/mandates/{session_id}` | `GET` | Path: `session_id` | If found: `session_id`, `total_budget`, `currency`. If 404: Session has no mandate yet. |

---

### 2.2 Dashboard (Buyer Overview)

The Dashboard synthesizes real persisted data without fabricating metrics:

| UI Widget | Data Source | Method | Parameters / Body | Processing & Calculations |
| :--- | :--- | :---: | :--- | :--- |
| **Total Purchases (KPI)** | `/api/checkout/history/{session_id}` | `GET` | `session_id`, `page=1`, `page_size=100` | Count orders where `status == "COMPLETED"`. Pending/failed orders are excluded. |
| **Total Spending (KPI)** | `/api/checkout/history/{session_id}` | `GET` | `session_id`, `page=1`, `page_size=100` | Sum of `total_amount` across `COMPLETED` orders. Display with transaction currency. |
| **Money Saved (KPI)** | `/api/checkout/orders/{id}` | `GET` | For recent completed orders | Sum `(compare_at_price - unit_price) * quantity` where `compare_at_price > unit_price`. If unavailable, display "$0.00" / "N/A". |
| **Active Budget (KPI)** | `/api/mandates/{session_id}` | `GET` | Path: `session_id` | `total_budget` minus `Total Spending`. Show budget utilization percentage. |
| **Recent Purchases Table** | `/api/checkout/history/{session_id}` | `GET` | `session_id`, `page=1`, `page_size=5` | Display `internal_order_number`, `total_amount`, `currency`, `created_at`, `status`. Clicking row opens order modal. |
| **Spending by Category Chart**| `/api/checkout/orders/{id}` | `GET` | Fetch items for completed orders | Group item subtotals by product category. Render Chart.js doughnut. Empty state if 0 purchases. |

---

### 2.3 AI Shopping Assistant

The AI Copilot page coordinates conversational query understanding, live product retrieval, and policy checking:

| UI Component | Action / Trigger | Backend Endpoint | Method | Payload / Parameters | Key Response Fields Used |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **Chat Message Box** | User submits shopping query | `/api/assistant/query` | `POST` | ```json { "session_id": "...", "query": "Find me a laptop for AI under ₹70,000", "conversation_context": [...] } ``` | `assistant_message`, `intent`, `products`, `eligibility_details`, `ai_analyses`, `is_ai_degraded` |
| **Intent Extraction Banner**| Rendered above recommendations | — | — | Derived from response: `intent.category`, `intent.max_budget`, `intent.currency`, `intent.required_specs` | Displays extracted constraints so user knows what AI understood. |
| **Eligibility Badges** | Rendered on each product card | — | — | Derived from `eligibility_details`: `QUALIFIED` (green), `CURRENCY_MISMATCH` (amber), `UNVERIFIED_SPECS` (blue), `EXCLUDED` (red) | Informs user whether product meets hard constraints. |
| **AI Intelligence Drawer**| Click "View AI Analysis" on card | — | — | Derived from `ai_analyses`: `strengths`, `weaknesses`, `intended_use_advantages`, `tradeoffs`, `value_for_money_explanation` | Explainable AI rationale for each product. |
| **Degraded Mode Alert** | If AI provider experienced failure | — | — | `is_ai_degraded == true`, `degraded_reason` | Subtle amber notice: "AI reasoning operating in deterministic fallback mode." |
| **Mandate Compliance Pill**| On recommendation cards | — | — | `mandate_evaluation.decision` ("ALLOWED" or "BLOCKED"), `mandate_evaluation.reasons` | Real-time policy feedback directly inside assistant view. |

---

### 2.4 Product Catalogue (Discovery & Search)

| UI Component | Action / Trigger | Backend Endpoint | Method | Parameters | Key Response Fields Used |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **Product Grid** | Page load or filter change | `/api/products` | `GET` | Query: `q`, `category`, `brand`, `min_price`, `max_price`, `source`, `page`, `page_size` | `items`, `total`, `page`, `total_pages`. Renders cards with lowest price, retailer, image. |
| **Live Aggregator Search** | User switches to "Live Channel3" tab | `/api/products/search` | `GET` | Query: `q`, `limit=12` | Live results from Channel3. Cards tagged with `Live Channel3` badge. |
| **Data Source Tag** | On each card | — | — | `item.is_synthetic` & `item.provider` | Distinct pill: `Synthetic Demo` vs `Live Retailer Listing`. |
| **Data Quality Warnings** | On product cards/details | — | — | `item.data_quality_warnings` | Ingested warnings (e.g., "Missing headphone style spec", "Unverified rating"). |

---

### 2.5 Product Details & Multi-Product Comparison

| UI Component | Action / Trigger | Backend Endpoint | Method | Parameters | Key Response Fields Used |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **Product Detail Modal** | Click product card | `/api/products/{id}` | `GET` | Path: `id` | Full specifications (`specifications`), all competing offers (`offers`), lowest price retailer (`lowest_price_retailer`). |
| **Retailer Offers Table**| Inside detail modal | — | — | `offers` array | List of stores (`retailer_name`), prices (`price`, `compare_at_price`), stock status (`availability`), direct link (`product_url`). |
| **Comparison Matrix** | Select 2–4 products & click "Compare" | `/api/products/compare` | `GET` | Query: `ids=prod_1&ids=prod_2` (or `ids=prod_1,prod_2`) | `comparison_matrix` (spec key to product values), `price_summary`, `products`. Renders side-by-side spec table. |
| **Cross-Currency Warning** | In comparison matrix | — | — | Checked across `products[i].currency` | Amber banner if currencies differ (e.g. USD vs INR): "Direct price comparison unavailable without FX rates." |

---

### 2.6 Spending Mandates

| UI Component | Action / Trigger | Backend Endpoint | Method | Payload / Parameters | Key Response Fields Used |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **Mandate Card / View** | Load Mandates page | `/api/mandates/{session_id}` | `GET` | Path: `session_id` | `total_budget`, `maximum_item_price`, `maximum_quantity`, `currency`, `created_at`. |
| **Create Mandate Form** | Submit new mandate | `/api/mandates` | `POST` | ```json { "session_identifier": "...", "total_budget": 1000.0, "maximum_item_price": 500.0, "maximum_quantity": 2, "currency": "USD" } ``` | Returns created `SpendingMandateResponse`. Updates local state. |
| **Update Mandate Form** | Edit budget ceilings | `/api/mandates/{session_id}` | `PUT` | ```json { "total_budget": 1500.0, "maximum_item_price": 750.0 } ``` | Returns updated `SpendingMandateResponse`. |
| **Test Purchase Policy**| Pre-flight check before checkout | `/api/mandates/{session_id}/validate` | `POST` | ```json { "unit_price": 249.99, "quantity": 1, "currency": "USD" } ``` | `decision` ("ALLOWED" or "BLOCKED"), `is_allowed`, `reasons`, `remaining_budget_after_purchase`. |

---

### 2.7 Checkout & Payment Subsystem (PayPal Sandbox)

| UI Step | Action / Trigger | Backend Endpoint | Method | Payload / Parameters | Expected Outcomes |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **1. Initiate Checkout** | Click "Proceed to Checkout" | `/api/checkout/orders` | `POST` | ```json { "session_identifier": "guest_...", "currency": "USD", "items": [{ "product_id": "...", "retailer_offer_id": "...", "product_name": "...", "quantity": 1, "unit_price": "99.99", "currency": "USD" }] } ``` | **Track A (Demo Item):** Returns HTTP 201 with `PaymentOrderResponse` containing `approval_url`, `id`, `paypal_order_id`.<br>**Track B (External Item):** Returns HTTP 400 with `ExternalRetailerCheckoutError` redirect payload. |
| **2. External Retailer Redirect** | On Track B response | — | — | `requires_external_checkout: true`, `retailer_name`, `product_url`, `price` | Displays confirmation dialog: "This item is sold by [Merchant]. You will complete purchase on their site." Opens `product_url`. |
| **3. PayPal Approval** | On Track A response | User completes approval in PayPal Sandbox popup | — | Opened URL: `approval_url` | User logs into PayPal Sandbox buyer account and approves payment. |
| **4. Backend Capture** | On return from PayPal | `/api/checkout/orders/{id}/capture` | `POST` | Query: `session_id={session_id}` | Executes backend capture, verifies `COMPLETED` status, amount, and currency. Returns updated order with status `COMPLETED`. |
| **5. Order Status Query**| Fallback / verification probe | `/api/checkout/orders/{id}` | `GET` | Query: `session_id={session_id}` | Returns authoritative `PaymentOrderResponse` with items and captures. |

---

### 2.8 Purchase History & Transaction Receipts

| UI Component | Action / Trigger | Backend Endpoint | Method | Parameters | Key Response Fields Used |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **Orders Table** | Load My Purchases page | `/api/checkout/history/{session_id}` | `GET` | Query: `page=1`, `page_size=20` | `orders` array: `internal_order_number`, `status`, `total_amount`, `currency`, `item_count`, `created_at`, `captured_at`. |
| **Order Receipt Modal**| Click on an order row | `/api/checkout/orders/{id}` | `GET` | Query: `session_id={session_id}` | Itemized snapshots (`items`), verified capture reference (`captures`), masked payer email, timestamps. |

---

### 2.9 Settings & Help Center

| UI Section | Backend Dependency | Notes |
| :--- | :--- | :--- |
| **Session Info** | `localStorage` + `/api/mandates/{session_id}` | Displays active guest session UUID, option to reset session, and active mandate. |
| **Currency Preference**| Client-side state | Preferred display currency (does not perform unverified numerical conversions). |
| **Security & Sandbox Notice** | Static / `/health` | Informs user that checkout runs strictly in PayPal Sandbox environment (`https://api-m.sandbox.paypal.com`). |
| **Help & FAQ** | Static | Explains AI eligibility states, spending mandates, difference between demo checkout and external marketplace checkout. |

---

## 3. RFC 9457 Error Response Handling

All API errors conform to `ProblemDetail`:

```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": {
    "error": "mandate_policy_violation",
    "message": "Purchase violates active spending mandate limits.",
    "reasons": ["Purchase total USD 1200.00 exceeds remaining budget USD 500.00"]
  },
  "instance": "/api/checkout/orders"
}
```

The frontend API client will intercept these and display human-readable toast notifications and contextual inline alert banners based on `detail.message` or `detail.reasons`.
