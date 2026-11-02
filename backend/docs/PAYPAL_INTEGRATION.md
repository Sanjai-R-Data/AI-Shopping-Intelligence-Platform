# PayPal Sandbox REST Client & Checkout Architecture

> **AI-Powered Multilingual Shopping Intelligence Platform**  
> **Milestone:** Phase 4.2 — PayPal Sandbox REST Client & Checkout Service  
> **Status:** Completed & Authoritatively Verified  
> **Environment:** PayPal Sandbox Only (`https://api-m.sandbox.paypal.com`)

---

## 1. Executive Summary & Architecture Overview

The AI-Powered Shopping Intelligence Platform provides an intelligent, responsible e-commerce discovery and purchasing workflow. In Phase 4.2, the backend checkout pipeline was implemented using the **PayPal Orders v2 REST API** strictly within the PayPal Sandbox environment.

### Core Architectural Invariants

1. **Dual Purchase Path Distinction:**
   - **Synthetic In-Catalog Items:** Fulfillable directly through our internal demo store gateway using PayPal Sandbox.
   - **Channel3 External Marketplace Offers:** Real retailer offers (e.g., Walmart, Best Buy, Newegg) discovered via Channel3 are strictly non-fulfillable via internal demo checkout. Any checkout request containing a non-synthetic item is deterministically rejected with an HTTP 400 `ExternalRetailerCheckoutError` containing a structured redirection payload (`requires_external_checkout: True`, merchant name, product URL, price, currency) so the buyer can complete their purchase directly on the merchant's store.

2. **Authoritative Backend-Controlled Verification:**
   - Client applications never dictate payment completion. The backend independently captures orders and authoritatively validates the capture payload:
     - PayPal Capture status must be exactly `COMPLETED`.
     - Settled capture currency must match the internal order currency.
     - Settled capture gross amount must exactly equal the internal order total (using exact string/Decimal equality).
     - Capture transaction ID must be unique across all database captures (replay attack prevention).

3. **Decoupled Database Transactions & Concurrency Safety:**
   - Database transactions are never held open while waiting for external PayPal REST network I/O.
   - Each state transition follows a two-phase transaction pattern: local record state persistence $\rightarrow$ external HTTP call $\rightarrow$ state finalization transaction.

4. **Independent Idempotency Identifiers:**
   - **Order Creation Idempotency:** `paypal_request_id` (UUIDv4) is persisted in `payment_orders.paypal_request_id` and transmitted as the `PayPal-Request-Id` header during `POST /v2/checkout/orders`.
   - **Order Capture Idempotency:** `paypal_capture_request_id` (UUIDv4) is persisted in `payment_orders.paypal_capture_request_id` upon entering `CAPTURE_PENDING` and transmitted as the `PayPal-Request-Id` header during `POST /v2/checkout/orders/{id}/capture`.
   - Using distinct identifiers prevents key reuse violations across PayPal endpoints while allowing deterministic network retry replay.

---

## 2. Component Structure

The checkout subsystem consists of five primary layers:

```
backend/app/
├── core/
│   ├── config.py                 # Sandbox URL enforcement, credentials, timeouts
│   └── database.py               # Schema compatibility migration for paypal_capture_request_id
├── models/
│   └── payment.py                # PaymentOrder, OrderItem, PaymentCapture SQLAlchemy models
├── schemas/
│   └── checkout.py               # CheckoutOrderCreate, CaptureOrderRequest, PaymentOrderResponse
├── services/
│   ├── paypal_client.py          # Low-level PayPal Orders v2 REST API client
│   └── checkout_service.py       # High-level checkout orchestrator and business rules
└── api/
    └── checkout.py               # FastAPI checkout routes (/api/checkout/*)
```

---

## 3. PayPal Client Implementation (`paypal_client.py`)

### 3.1 Authentication & Token Lifecycle

- **Endpoint:** `POST https://api-m.sandbox.paypal.com/v1/oauth2/token`
- **Method:** HTTP Basic Authentication using `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`.
- **Payload:** `grant_type=client_credentials`
- **Caching & Expiration:**
  - Token is cached in-memory with thread-safe locking (`threading.Lock`).
  - Cache expires `300 seconds` prior to the actual token lifetime (`expires_in`) to prevent edge-of-expiry race conditions.
  - Automatic refresh occurs seamlessly when the cached token expires.

### 3.2 Error Handling & Logging

All PayPal REST errors are mapped into strongly-typed exceptions:
- `PayPalAuthError` (HTTP 401 / Invalid Credentials)
- `PayPalRateLimitError` (HTTP 429 / Rate Limit Exceeded with `Retry-After`)
- `PayPalTimeoutError` (HTTP 408 / Socket Timeout)
- `PayPalOrderNotFoundError` (HTTP 404 / Order Missing)
- `PayPalCaptureError` (HTTP 422 / Capture Unprocessable or Already Captured)
- `PayPalAPIError` (General 4xx/5xx API Errors)

All logging sanitizes secrets: bearer tokens, client secrets, and sensitive buyer PII are never emitted to logs or traces.

---

## 4. End-to-End Checkout Flow

```
[Buyer / Frontend]          [FastAPI Checkout API]          [Database]           [PayPal Sandbox API]
        |                              |                         |                        |
  1.    |-- POST /api/checkout/orders ->|                         |                        |
        |                              |-- 2. Verify Session --->|                        |
        |                              |-- 3. Verify Items ----->|                        |
        |                              |      (Reject Channel3)  |                        |
        |                              |-- 4. Check Mandate ---->|                        |
        |                              |-- 5. DB Tx 1: Draft --->|                        |
        |                              |      (Status: CREATED)  |                        |
        |                              |-- 6. POST /v2/orders --------------------------->|
        |                              |<- 7. Order ID & Approval URL --------------------|
        |                              |-- 8. DB Tx 2: Update -->|                        |
        |<- 9. Return Order & Link ----|                         |                        |
        |                              |                         |                        |
 10.    |== Buyer Approves Order on Sandbox UI ==========================================>|
        |                              |                         |                        |
 11.    |-- POST .../orders/{id}/capture ->|                     |                        |
        |                              |-- 12. DB Tx 1: -------->|                        |
        |                              |   Status: CAPTURE_PENDING                        |
        |                              |   Set paypal_capture_req_id                      |
        |                              |-- 13. POST .../capture ------------------------->|
        |                              |<- 14. Capture Details & Status ------------------|
        |                              |-- 15. Verify Capture ---|                        |
        |                              |       (Amount, Currency,|                        |
        |                              |        Status==COMPLETED|                        |
        |                              |-- 16. DB Tx 2: -------->|                        |
        |                              |   Status: COMPLETED     |                        |
        |                              |   Save PaymentCapture   |                        |
        |<- 17. Return Verified Order -|                         |                        |
```

---

## 5. Security & Verification Invariants

### 5.1 Amount and Currency Invariant Check

When PayPal responds to `capture_order`, `CheckoutService` extracts the settled amounts from `purchase_units[0].payments.captures[0]`.
The following assertions must hold:
1. `capture_status == "COMPLETED"` (Orders in `PENDING`, `DECLINED`, or `FAILED` are rejected).
2. `Decimal(capture_amount) == Decimal(order.total_amount)` (Prevents partial capture fraud or price manipulation).
3. `capture_currency.upper() == order.currency.upper()` (Prevents currency confusion attacks).

### 5.2 Network Timeout Reconciliation Probe

If a timeout occurs during `POST /v2/checkout/orders/{id}/capture`, the capture state at PayPal is ambiguous:
1. `CheckoutService` catches `PayPalTimeoutError`.
2. It immediately issues an authoritative `GET /v2/checkout/orders/{order_id}` query.
3. If the order status is already `COMPLETED` and a verified capture exists, it proceeds with settlement completion.
4. If the order remains uncaptured, the timeout error is raised so the client can safely retry using the existing `paypal_capture_request_id`.

---

## 6. API Reference

### 6.1 Initiate Checkout Order

- **Endpoint:** `POST /api/checkout/orders`
- **Request Body:**
```json
{
  "session_identifier": "guest_session_9148",
  "currency": "USD",
  "idempotency_key": "optional-client-key-1234",
  "items": [
    {
      "product_id": "prod_d964f488e0ec",
      "retailer_offer_id": "off_2b5d4bafe9a7",
      "product_name": "Soundcore Space One",
      "quantity": 1,
      "unit_price": "99.99",
      "currency": "USD"
    }
  ]
}
```
- **Response (HTTP 201 Created):**
```json
{
  "id": "ord_1067b0eb81ec",
  "internal_order_number": "ORD-20261102-12AB34CD",
  "session_id": "sess_84e1b8c68c34",
  "status": "CREATED",
  "total_amount": "99.99",
  "currency": "USD",
  "payment_provider": "paypal_sandbox",
  "paypal_order_id": "5O3621571680TN364715T",
  "approval_url": "https://www.sandbox.paypal.com/checkoutnow?token=5O3621571680TN364715T",
  "created_at": "2026-11-02T12:00:00Z"
}
```

### 6.2 External Retailer Rejection (Channel3 Items)

If any item is from an external merchant provider (Channel3):
- **Response (HTTP 400 Bad Request):**
```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": {
    "error": "external_retailer_checkout",
    "message": "Item 'External Smart Watch' is sold by external merchant 'Walmart'. You will complete your purchase directly on their website.",
    "retailer_name": "Walmart",
    "product_name": "External Smart Watch",
    "product_url": "https://walmart.com/garmin-watch",
    "price": "249.99",
    "currency": "USD",
    "requires_external_checkout": true
  },
  "instance": "/api/checkout/orders"
}
```

### 6.3 Capture Approved Order

- **Endpoint:** `POST /api/checkout/orders/{order_id}/capture`
- **Request Body:**
```json
{
  "session_identifier": "guest_session_9148"
}
```
- **Response (HTTP 200 OK):**
```json
{
  "id": "ord_1067b0eb81ec",
  "internal_order_number": "ORD-20261102-12AB34CD",
  "session_id": "sess_84e1b8c68c34",
  "status": "COMPLETED",
  "total_amount": "99.99",
  "currency": "USD",
  "payment_provider": "paypal_sandbox",
  "paypal_order_id": "5O3621571680TN364715T",
  "captures": [
    {
      "id": "cap_8f7b2a9e",
      "paypal_capture_id": "2C123456789012345",
      "status": "COMPLETED",
      "amount": "99.99",
      "currency": "USD",
      "created_at": "2026-11-02T12:05:00Z"
    }
  ]
}
```

### 6.4 Query Order Status

- **Endpoint:** `GET /api/checkout/orders/{order_id}`
- **Response (HTTP 200 OK):** Returns full `PaymentOrderResponse` with items and captures.

### 6.5 Session Payment History

- **Endpoint:** `GET /api/checkout/history/{session_id}`
- **Response (HTTP 200 OK):** Returns list of all orders associated with the guest session.

---

## 7. Manual Testing with PayPal Sandbox

To test the entire checkout flow manually:

1. **Verify Sandbox Credentials:**
   Ensure `.env` contains:
   ```dotenv
   PAYPAL_CLIENT_ID=your_sandbox_client_id
   PAYPAL_CLIENT_SECRET=your_sandbox_client_secret
   PAYPAL_MODE=sandbox
   ```

2. **Run the Backend:**
   ```powershell
   .\.venv\Scripts\python -m uvicorn backend.app.main:app --reload
   ```

3. **Create Order:**
   Submit `POST /api/checkout/orders` with demo catalog items. Note the returned `approval_url` and `id`.

4. **Buyer Approval:**
   Open the `approval_url` in an Incognito browser window. Log in using a PayPal Sandbox Personal Buyer Account (`sb-buyer@business.example.com`) and click **"Complete Purchase"**.

5. **Capture Order:**
   Submit `POST /api/checkout/orders/{id}/capture` to trigger backend capture and authoritative verification.
