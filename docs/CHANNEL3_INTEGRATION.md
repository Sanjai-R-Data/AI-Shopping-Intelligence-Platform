# Channel3 Live Product Aggregation Architecture & Integration Guide

**Platform:** AI-Powered Multilingual Shopping Intelligence Platform  
**Document Version:** 1.0.0  
**Phase:** Phase 2 — Channel3 Live Aggregation  

---

## 1. Executive Summary

This document specifies the integration of **Channel3** (`https://channel3.ai/`) as the platform's primary live product discovery and multi-retailer aggregation provider. 

Channel3 indexes over 100 million products across tens of thousands of online retailers (including Amazon, Best Buy, Newegg, Crutchfield, Target, Micro Center, etc.). This integration allows the platform to ingest real-world products, prices, and competing merchant offers while maintaining deterministic spending mandate enforcement and strict credit protection.

---

## 2. Integration Architecture

```
                                    +-----------------------------+
                                    |       User / Frontend       |
                                    +--------------+--------------+
                                                   |
                                                   | GET /api/products/search?q=...
                                                   v
                                    +-----------------------------+
                                    |     FastAPI Route Layer     |
                                    |   (backend/app/api/         |
                                    |       products.py)          |
                                    +--------------+--------------+
                                                   |
                                                   v
                                    +-----------------------------+
                                    |       ProductService        |
                                    +--------------+--------------+
                                                   |
                     +-----------------------------+-----------------------------+
                     |                                                           |
                     v                                                           v
       +----------------------------+                             +----------------------------+
       |       Channel3Client       |                             |     ProductRepository      |
       |  - POST /v1/search         |                             |  - upsert_channel3_product |
       |  - GET /v1/products/{id}   |                             |  - list_products (source)  |
       |  - Strict Credit Guards    |                             |  - get_by_provider_id      |
       +-------------+--------------+                             +--------------+-------------+
                     |                                                           |
                     v                                                           v
       +----------------------------+                             +----------------------------+
       |     Channel3Normalizer     |                             |       SQLite / WAL         |
       |  - Currency Preservation   |                             |    (shopping_platform.db)  |
       |  - Nullable Safe Mapping   |============================>|  - products                |
       |  - Clean Domain Extraction |                             |  - retailer_offers         |
       +----------------------------+                             +----------------------------+
```

---

## 3. Environment & Authentication Configuration

### Required Environment Variables

All secrets are loaded strictly via Pydantic Settings (`backend.app.core.config.Settings`) from the repository root `.env` file. Secrets are wrapped in `SecretStr` to prevent leakage in application logs, exceptions, and serialization.

| Variable Name | Type | Default | Description |
|---|---|---|---|
| `CHANNEL3_API_KEY` | `SecretStr` | `None` | Channel3 API key passed in `x-api-key` HTTP header. Never printed or logged. |
| `CHANNEL3_BASE_URL` | `str` | `https://api.trychannel3.com` | Channel3 REST API base endpoint. |
| `CHANNEL3_TIMEOUT_SECONDS` | `float` | `10.0` | HTTP request timeout for live external calls. |

### Configuration Template (`.env.example`)

```bash
# Channel3 API Configuration (Live Product Discovery)
CHANNEL3_API_KEY="your-channel3-api-key-here"
CHANNEL3_BASE_URL="https://api.trychannel3.com"
CHANNEL3_TIMEOUT_SECONDS=10.0
```

---

## 4. Search & Aggregation Workflow

1. **Incoming Request:** User or client invokes `GET /api/products/search?q={query}&limit={1..30}`.
2. **Channel3 Search:** `Channel3Client` dispatches an authenticated HTTP POST request to `https://api.trychannel3.com/v1/search` with payload `{"query": query, "limit": limit}`.
3. **Provider Validation:** The response status code is inspected:
   - `200 OK`: Valid JSON payload passed to normalizer.
   - `401 / 403`: Raises `Channel3AuthError` -> maps to `502 Bad Gateway` Problem Details.
   - `429 Too Many Requests`: Parses `Retry-After` header, raises `Channel3RateLimitError` -> maps to `429 Too Many Requests` Problem Details.
   - `5xx`: Raises `Channel3ServerError` -> maps to `502 Bad Gateway` Problem Details.
   - Timeout: Raises `Channel3TimeoutError` -> maps to `504 Gateway Timeout` Problem Details.
4. **Data Normalization:** `Channel3Normalizer` maps raw fields into canonical `NormalizedProduct` and `NormalizedOffer` DTOs.
5. **Idempotent Ingestion:** `ProductRepository.upsert_channel3_product` saves canonical records into SQLite. If the provider ID (`provider_product_id`) already exists, existing fields are refreshed and old offers are updated with fresh prices and retrieval timestamps.
6. **Standardized Delivery:** Normalized `ProductListResponse` is returned to the caller with clear provenance (`is_synthetic: false`, `provider: "channel3"`).

---

## 5. Normalization Logic & Field Mapping

| Channel3 Raw Field | Target Model Field | Mapping Rules & Fallbacks |
|---|---|---|
| `id` | `Product.provider_product_id` | Preserved verbatim (e.g. `"zNQps8G"`). Stable foreign key. |
| `title` | `Product.name` | Stripped string. Skips item if null or whitespace. |
| `brands[0].name` | `Product.brand` | Extracted from first brand item. Fallback: `"Unknown"`. |
| `category.title` | `Product.category` | Extracted from `title` or `slug`. Fallback: `"General"`. |
| `description` | `Product.description` | Sanitized text string. Fallback: `""`. |
| `images[*].cleaned_url` | `Product.image_url` | Prefers `is_main_image` item with `cleaned_url`. Fallback: `url` or `None`. |
| `structured_attributes` | `Product.specifications` | Flattened key-value dictionary. Merges `key_features` and `materials`. |
| `"channel3"` | `Product.provider` | Provider provenance tag. |
| `False` | `Product.is_synthetic` | Marks product as verified live aggregate data. |
| `offers[*].domain` | `RetailerOffer.retailer_name`| Retailer domain name (e.g. `"bestbuy.com"`, `"newegg.com"`). |
| `offers[*].price.price`| `RetailerOffer.price` | Numerical price (float). Skips offer if missing or `<= 0`. |
| `offers[*].price.currency`| `RetailerOffer.currency` | Original ISO-4217 currency (e.g. `"USD"`). Never mutated. |
| `offers[*].price.compare_at_price`| `RetailerOffer.compare_at_price` | List/original price before discount, when present. |
| `offers[*].url` | `RetailerOffer.product_url` | Direct outbound affiliate or retailer checkout URL. |
| `offers[*].availability`| `RetailerOffer.availability` | Normalized: `"InStock"` -> `"IN_STOCK"`, `"OutOfStock"` -> `"OUT_OF_STOCK"`. |
| UTC Now | `RetailerOffer.retrieved_at` | Timestamp of offer retrieval for freshness auditing. |

---

## 6. Credit Protection & Usage Invariants

Channel3 credit consumption is protected by strict architectural invariants:

1. **No Automated Retry Loops:** Potentially billable requests fail fast without automatic retry storms.
2. **Minimal Limits:** Search queries default to `limit=10` with a strict hard ceiling of `limit=30`.
3. **No Startup Calls:** The application never invokes Channel3 during startup, health checks, or database migrations.
4. **Mocked Automated Testing:** All automated tests (`backend/tests/test_channel3.py`) use mocked HTTPX transports. Zero live credits are consumed during test suites.
5. **Free Product Lookups:** Per official documentation, `GET /v1/products/{id}` is a free endpoint used for targeted offer refresh and revalidation.

---

## 7. Synthetic Data vs. Live Aggregation Invariants

1. **Strict Provenance:** Every product and retailer offer carries an `is_synthetic: bool` indicator and `provider: str` tag (`"synthetic"` or `"channel3"`).
2. **No Silent Fallback:** If Channel3 is unreachable, unauthenticated, rate-limited, or returns an error, the system **never** silently replaces live search results with synthetic demo products. An explicit RFC 9457 Problem Details error is returned.
3. **Coexistence:** Synthetic demo items and live Channel3 items can coexist safely in the local database. Clients can query `GET /api/products?source=synthetic`, `GET /api/products?source=live`, or retrieve both seamlessly.
4. **Product Comparison:** Users can compare live Channel3 products against synthetic demo products or other live products via `GET /api/products/compare?ids={id1}&ids={id2}`.

---

## 8. Offer Freshness & Purchase Safety

1. **Timestamp Auditing:** Every offer records `retrieved_at` (UTC timestamp).
2. **Deterministic Spending Mandate Policy:**
   - The deterministic policy engine (`SpendingPolicyEngine.evaluate`) enforces total budget, item ceiling, and quantity limits against live offer prices.
   - AI models cannot override or bypass this policy.
3. **Pre-Purchase Revalidation:** Before future checkout flows, `ProductService.revalidate_offer_freshness` fetches a fresh snapshot via `GET /v1/products/{product_id}` to guarantee price and stock availability before payment authorization.

---

## 9. Automated Testing Instructions

Run the Channel3 test suite:
```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_channel3.py -v
```

Run the entire platform test suite (48 tests):
```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -v
```

All 15 Channel3 test scenarios pass without external network traffic:
1. `test_successful_provider_response`
2. `test_product_normalization`
3. `test_retailer_offer_normalization`
4. `test_multiple_offers_for_one_product`
5. `test_missing_optional_fields`
6. `test_duplicate_products_upsert`
7. `test_invalid_provider_response`
8. `test_authentication_failure`
9. `test_rate_limit_response`
10. `test_timeout_handling`
11. `test_empty_search_results`
12. `test_provider_failure_without_synthetic_fallback`
13. `test_existing_product_api_compatibility`
14. `test_product_comparison_compatibility`
15. `test_spending_policy_engine_compatibility`

---

## 10. Known Limitations & Future Enhancements

1. **Marketplace Currencies:** Channel3 currently aggregates primarily US/international merchants (Newegg, Best Buy, Crutchfield, etc.) returning USD pricing. Regional Indian merchants returning INR (e.g. Amazon India, Flipkart) were not observed in US queries; multi-currency FX conversion will be incorporated in Phase 3.
2. **Image CDNs:** Product images are served via Channel3's CDN (`cdn.trychannel3.com`). Fallbacks to placeholder hero images are implemented when image assets are omitted by the merchant.
