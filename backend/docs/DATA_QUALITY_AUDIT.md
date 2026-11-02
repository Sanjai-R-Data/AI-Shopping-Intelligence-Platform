# Live Product Data Quality, Taxonomy Consistency & Comparison Audit

**Platform:** AI-Powered Multilingual Shopping Intelligence Platform  
**Document Version:** 1.0.0  
**Phase:** Phase 2.2 — Data Quality & Comparison Validation  

---

## 1. Executive Summary

Following the successful integration of Channel3 live product aggregation, a comprehensive quality and consistency audit was performed on live responses, database persistence, and comparison calculations.

This audit:
1. Root-causes four observed product anomalies (brand misattribution, taxonomy conflicts, model number variances, and stringified ratings).
2. Distinguishes upstream provider scraping artifacts from application normalization defects.
3. Implements non-destructive validation, transparent warnings, and numeric type coercion.
4. Enforces critical currency-safety safeguards ensuring mixed currencies (e.g. USD vs INR) are never directly compared.
5. Extends automated test coverage to 66 passing test suites with zero live credit consumption.

---

## 2. Inconsistency Investigation & Root Cause Analysis

| Observed Issue | Evidence in Raw Data | Origin | Root Cause & Resolution |
|---|---|---|---|
| **1. Anker Soundcore Space One brand is `Nebula Robotics`** | `brands: [{"id": "KDuu", "name": "Nebula Robotics"}]` | **Channel3 (Upstream)** | Anker Innovations owns both *Soundcore* (audio) and *Nebula* (smart projectors). Channel3's merchant scraping linked the parent company's Nebula entity to this Soundcore listing. **Resolution:** We preserve the raw brand (`"Nebula Robotics"`) to maintain provenance, but detect the discrepancy and emit a transparent data quality warning: `"Brand discrepancy: title mentions 'Anker' but provider assigned brand is 'Nebula Robotics'."` |
| **2. JVC HAS59WA Over-Ear Category vs Ear hooks style** | `category: {"title": "Over-Ear Headphones"}`, `structured_attributes: {"headphone-style": ["Ear hooks"]}` | **Channel3 (Upstream)** | Category taxonomy was assigned as `"Over-Ear Headphones"` by Channel3's classifier, while merchant attribute scraping from Micro Center extracted `"Ear hooks"`. **Resolution:** We preserve both fields without guessing, and emit a taxonomy warning: `"Taxonomy discrepancy: category is 'Over-Ear Headphones' but headphone-style specification is 'Ear hooks'."` |
| **3. JVC title and description model name variance** | `title: "HAS59WA..."`, `description: "JVC HAS59W..."` | **Channel3 (Upstream)** | Merchant title specifies SKU/color variant `"HAS59WA"` (blue variant), while manufacturer copy references model family `"HAS59W"`. **Resolution:** Both strings are preserved verbatim. Suffix variances are detected and flagged. |
| **4. Ratings represented as strings** | `ratings: {"value": 4.14, "count": 108}` | **Application Normalizer (Local)** | Channel3 provided `ratings.value` as a numeric float (`4.14`), but our normalizer explicitly stringified it (`str(ratings.get("value"))`). **Resolution:** Refactored normalizer with `_parse_rating` to validate floats between `0.0` and `5.0` (with 10-point scale normalization) and integers for review counts. Non-numeric or out-of-bounds ratings safely become `None`. |

---

## 3. Normalization Improvements Implemented

1. **Numeric Rating Enforcement:**
   - Ratings are strictly represented as `float` (clamped `0.0 <= val <= 5.0`, rounded to 2 decimals).
   - Review counts are strictly represented as `int` (`count >= 0`).
   - Invalid formats (e.g. `"four stars"`, negative numbers, NaN) safely evaluate to `None` without crashing or fabricating fallback scores.
2. **Provenance & Data Quality Warnings:**
   - Introduced `data_quality_warnings: list[str]` on [`ProductBase`](file:///c:/Users/SANJAI-R/Desktop/AI-Shopping-Intelligence-Platform/backend/app/schemas/product.py#L43), [`ProductResponse`](file:///c:/Users/SANJAI-R/Desktop/AI-Shopping-Intelligence-Platform/backend/app/schemas/product.py#L62), and [`ProductCompareItem`](file:///c:/Users/SANJAI-R/Desktop/AI-Shopping-Intelligence-Platform/backend/app/schemas/product.py#L88).
   - Warnings highlight brand mismatches, taxonomy conflicts, and model SKU variances without altering or guessing provider data.
3. **Verbatim Text Preservation:**
   - Product titles and descriptions are preserved faithfully, retaining Unicode characters (e.g. narrow no-break space `\u202f` and non-breaking hyphens `\u2011`).
4. **Distinct Variant Isolation:**
   - Products are uniquely keyed by `(provider, provider_product_id)`. Variant SKUs (e.g. HAS59WA Blue vs HAS59WB Black) remain distinct database records.

---

## 4. Retailer Offer Integrity

1. **One-to-Many Offer Associations:** Canonical products maintain multiple competing retailer offers without duplication.
2. **Currency Preservation:** The original ISO-4217 currency code (e.g. `USD`, `INR`) is preserved uppercase on every offer.
3. **Optional Compare-At Pricing:** `compare_at_price` is populated only when supplied and strictly greater than the purchase price; otherwise `None`.
4. **Verified Availability:** Standardized stock status (`IN_STOCK`, `LIMITED_STOCK`, `OUT_OF_STOCK`).
5. **Exact Outbound URLs:** Complete affiliate and merchant buy URLs are stored without modification.
6. **Freshness Auditing:** `retrieved_at` timestamps in UTC track when offer prices were captured.

---

## 5. Comparison Engine & Currency Safeguards

### Currency-Safe Lowest Price Calculations
- In [`Product.lowest_price(currency=None)`](file:///c:/Users/SANJAI-R/Desktop/AI-Shopping-Intelligence-Platform/backend/app/models/shopping.py#L70), lowest price is evaluated only within the target currency or the product's primary currency. Offers in different currencies are never combined numerically.
- Added [`Product.lowest_price_offer()`](file:///c:/Users/SANJAI-R/Desktop/AI-Shopping-Intelligence-Platform/backend/app/models/shopping.py#L78) to return the exact [`RetailerOffer`](file:///c:/Users/SANJAI-R/Desktop/AI-Shopping-Intelligence-Platform/backend/app/models/shopping.py#L112) granting the lowest price.

### Cross-Currency Safeguard (USD vs INR)
- In `ProductService.compare_products`:
  - Currencies across all compared items are inspected.
  - **Single Currency:** Standard price summary computes `cheapest_product`, `cheapest_price`, `cheapest_retailer`, and market price bounds.
  - **Multiple Currencies (e.g. USD and INR):**
    - Direct cross-currency numeric ranking is **strictly disabled**:
      - `price_summary.is_multi_currency = True`
      - `price_summary.currency = "MIXED"`
      - `price_summary.cheapest_product = None`
      - `price_summary.cheapest_price = None`
      - `price_summary.warning = "Direct cross-currency comparison disabled: products use multiple currencies (INR, USD). FX conversion is required to rank prices across currencies."`
    - Provides a safe `by_currency` breakdown showing the lowest price within each currency bucket.

### Specification & Score Invariants
- Missing specifications in the comparison matrix are clearly represented as `"Not Specified"`.
- Missing prices remain `None` and never become `0.0`.
- Zero unsupported value-for-money scores or subjective metrics are fabricated.

---

## 6. Automated Testing Verification

All 66 tests across the test suite pass with 0 errors:

| Test File | Tests | Focus Area |
|---|---|---|
| `test_data_quality.py` | 18 | Brand heuristics, taxonomy conflicts, numeric rating validation, mixed currency safeguards, variant isolation, offer freshness, and mandate policy. |
| `test_channel3.py` | 15 | Live aggregation mocks, HTTP status handling, rate-limit headers, timeouts, duplicate upsert idempotency. |
| `test_products.py` | 9 | Catalog listing, facet filtering, price range boundaries, comparison matrix, detail retrieval. |
| `test_mandates.py` | 12 | Budget limits, item price ceilings, quantity ceilings, currency enforcement, RFC 9457 errors. |
| `test_health.py` | 6 | Health checks, database readiness probes, RFC 9457 error sanitization. |
| `test_database.py` | 3 | SQLite PRAGMAs (WAL, foreign keys, busy timeout), session lifecycle. |
| `test_config.py` | 3 | Settings initialization, `SecretStr` masking, SQLite URL normalization. |
| **Total** | **66** | **100% Passed in 4.97s** |

---

## 7. Unresolved Data Quality Limitations

1. **Merchant-Side Taxonomy Errors:** Upstream providers occasionally scrape ambiguous merchant tags (e.g. "Ear hooks" under "Over-Ear Headphones"). Our platform identifies and surfaces these contradictions via `data_quality_warnings`, but cannot fix retailer errors without human intervention or LLM reasoning.
2. **Upstream Corporate Parent Inconsistencies:** Multi-brand parent companies (e.g. Anker / Soundcore / Nebula) will continue to present scraping classification errors from third-party aggregators.
3. **Cross-Currency Normalization:** Until FX rates are formally integrated in a dedicated phase, multi-currency comparisons remain grouped per-currency with cross-currency ranking disabled.
