# BUYWISE AI — Frontend Implementation Plan & Phased Roadmap

> **System:** BUYWISE AI — AI-Powered Multilingual Shopping Intelligence Platform  
> **Tagline:** Discover smarter. Compare deeper. Spend responsibly.  
> **Audit Milestone:** Phase 1 — Repository and API Audit  
> **Document:** UI Implementation Plan & Roadmap  
> **Execution Strategy:** Phased, Test-Driven, Read-Only Boundary Enforced

---

## 1. Project Vision & Core Principles

BUYWISE AI bridges conversational artificial intelligence, multi-retailer product intelligence, deterministic financial spending policies, and PayPal Sandbox payments.

### Core Architectural Principle
> **"AI suggests. Backend validates. User approves. PayPal processes."**

The frontend architecture enforces this by design:
1. **Never authorize on the client:** Policy compliance, pricing totals, and payment completion are authoritatively verified by the backend.
2. **Never fabricate data:** KPIs, charts, and product ratings are derived strictly from persisted records. When records are missing, clear and attractive empty states are presented.
3. **Never blur synthetic vs live:** Synthetic demo items and live Channel3 retailer listings are visually and functionally distinguished at all times.
4. **Pure Vanilla JavaScript (No React / Vue):** Lightweight, zero-build, modular ES6 architecture served statically by FastAPI.

---

## 2. Visual Design System & Design Tokens

### 2.1 Color Palette

| Token Name | Hex Code | Usage |
| :--- | :--- | :--- |
| `--color-charcoal` | `#191919` | Sidebar background, primary text, dark accents |
| `--color-warm-ivory`| `#F5F1E8` | Main application canvas background |
| `--color-card-bg` | `#FFFFFF` | Content cards, data tables, modals |
| `--color-card-alt` | `#FAF7F2` | Subtle secondary card background, table headers |
| `--color-burnt-orange`| `#E88A38` | Primary call-to-action buttons, active highlights, checkout trigger |
| `--color-orange-hover`| `#D67A2A` | Hover state for primary buttons |
| `--color-muted-lime` | `#A5C94B` | Policy approved badges, success states, qualified specs |
| `--color-lime-dark` | `#2D5A27` | Text on lime pills for WCAG AA contrast |
| `--color-alert-red` | `#DC2626` | Mandate blocked badges, exclusion notices, error toasts |
| `--color-warning-amber`| `#D97706`| Currency mismatch badges, degraded mode notice |
| `--color-text-sec` | `#777777` | Secondary labels, descriptions, timestamps |
| `--color-border` | `#E5E0D5` | Card borders, table dividers (subtle warm gray) |

### 2.2 Typography
- **Headings & Brand:** `Manrope`, sans-serif (Font weights: 600, 700, 800)
- **Body & Controls:** `Inter`, sans-serif (Font weights: 400, 500, 600)
- **Code & Numerical Identifiers:** Monospace / `JetBrains Mono`

### 2.3 UI Components & Shape Language
- **Border Radiuses:** Cards: `14px` (`rounded-xl`), Buttons/Pills: `8px`–`9999px` (`rounded-lg` or `rounded-full`).
- **Shadows:** Soft, diffused elevation: `box-shadow: 0 4px 20px -2px rgba(25, 25, 25, 0.05);`
- **Iconography:** Professional SVG Lucide-style inline icons (no heavy external icon fonts).

---

## 3. Frontend Architecture & Directory Layout

The frontend will reside entirely within the `frontend/` directory:

```text
frontend/
├── index.html                  # Single-page application shell
├── css/
│   ├── tokens.css              # CSS custom properties (colors, typography, spacing)
│   └── styles.css              # Global layout, utility styles, custom scrollbars
├── js/
│   ├── app.js                  # Application bootstrapper & global event coordinator
│   ├── api.js                  # Centralized HTTP client with RFC 9457 error handling
│   ├── state.js                # Reactive store (session, mandate, cart, history)
│   ├── router.js               # Hash-based SPA routing (#dashboard, #assistant, etc.)
│   ├── components/
│   │   ├── navbar.js           # Top navigation bar (health pill, session status)
│   │   ├── sidebar.js          # Collapsible charcoal sidebar navigation
│   │   ├── product-card.js     # Dual-track product card (synthetic vs live)
│   │   ├── comparison-modal.js # Side-by-side comparison table
│   │   ├── checkout-modal.js   # PayPal Sandbox & external retailer checkout dialog
│   │   └── toast.js            # Toast notifications for success/error feedback
│   └── pages/
│       ├── dashboard.js        # KPI cards, real spending charts, recent orders
│       ├── assistant.js        # AI copilot conversation, eligibility pills, AI drawer
│       ├── catalogue.js        # Search, filters, live Channel3 toggle, pagination
│       ├── compare.js          # Dedicated multi-product comparison matrix view
│       ├── mandates.js         # Spending mandate configuration & policy tester
│       ├── purchases.js        # Persisted order history & verified capture receipts
│       └── settings.js         # Session configuration, environment disclosures, FAQ
└── assets/
    └── images/                 # Favicon, logo, and fallback product placeholders
```

---

## 4. Phased Implementation Roadmap

### Phase 2: Design System & Application Shell
- **Objectives:**
  1. Build `frontend/index.html`, `css/tokens.css`, and `css/styles.css`.
  2. Implement collapsible charcoal sidebar with active-page indicators.
  3. Implement top navigation bar with system health indicator (`GET /health`) and guest session indicator.
  4. Implement hash-based client-side router (`router.js`) supporting:
     - `#dashboard`, `#assistant`, `#catalogue`, `#compare`, `#mandates`, `#purchases`, `#settings`.
  5. Configure FastAPI static file serving in `backend/app/main.py`:
     - Serve `frontend/` static assets at `/static`.
     - Route `GET /` to `frontend/index.html` via `FileResponse` while keeping `/api/*`, `/health`, `/docs`, `/openapi.json` intact.
- **Verification:** Browser loads SPA layout cleanly; hash navigation toggles views; health check reports live database status.

### Phase 3: Dashboard (Buyer Overview)
- **Objectives:**
  1. Implement KPI metric cards: Total Spending, Total Purchases, Money Saved, Active Budget.
  2. Derive metrics strictly from `GET /api/checkout/history/{session_id}` and `GET /api/mandates/{session_id}`.
  3. Render Chart.js category spending distribution only if completed orders exist.
  4. Render recent completed purchases table with status pills.
  5. Provide polished empty states when no purchase history exists.
- **Verification:** Dashboard displays real calculated data for sessions with orders; displays graceful empty state for new guest sessions.

### Phase 4: AI Shopping Assistant
- **Objectives:**
  1. Build conversational chat stream with suggested prompts.
  2. Integrate `POST /api/assistant/query`.
  3. Render extracted shopping intent banner (budget, required specs, detected language).
  4. Render product recommendations with eligibility badges:
     - `QUALIFIED` (Green), `CURRENCY_MISMATCH` (Amber), `UNVERIFIED_SPECS` (Blue), `EXCLUDED` (Red).
  5. Render explainable AI analysis cards (strengths, weaknesses, trade-offs).
  6. Support degraded mode notification when Gemini is in deterministic fallback.
  7. Add "Test Mandate" and "Proceed to Checkout" actions directly on qualified cards.
- **Verification:** Assistant processes English, Tamil, Spanish, French queries; visualizes eligibility badges correctly; displays fallback alert when Gemini is unavailable.

### Phase 5: Product Catalogue & Comparison
- **Objectives:**
  1. Implement catalog grid connected to `GET /api/products` with search, category, brand, and price filters.
  2. Implement "Live Channel3" toggle calling `GET /api/products/search`.
  3. Display clear provenance tags: `Synthetic Demo` vs `Live Channel3 Listing`.
  4. Implement Product Detail modal with competing retailer offers table and lowest-price retailer.
  5. Implement multi-product selection and side-by-side comparison matrix via `GET /api/products/compare`.
  6. Enforce currency safety warnings if compared products have disparate currencies.
- **Verification:** Catalogue searches stored catalog and live Channel3; product detail displays offers; comparison matrix compares specs and warns on mixed currencies.

### Phase 6: Spending Mandates & Checkout (PayPal Sandbox)
- **Objectives:**
  1. Implement Mandate Management view (`POST /api/mandates`, `GET /api/mandates/{session_id}`, `PUT /api/mandates/{session_id}`).
  2. Implement pre-flight purchase policy tester (`POST /api/mandates/{session_id}/validate`).
  3. Build Checkout Modal with item summary, total, and explicit user confirmation.
  4. **Dual Purchase Path Execution:**
     - **Track A (Demo Item):** Calls `POST /api/checkout/orders` $\rightarrow$ receives PayPal `approval_url` $\rightarrow$ opens PayPal Sandbox popup $\rightarrow$ captures via `POST /api/checkout/orders/{id}/capture` $\rightarrow$ verifies `COMPLETED` settlement.
     - **Track B (Live Channel3 Item):** Calls `POST /api/checkout/orders` $\rightarrow$ receives HTTP 400 with `ExternalRetailerCheckoutError` $\rightarrow$ renders external redirection dialog with merchant link.
- **Verification:** Track A completes sandbox payment and verified capture; Track B cleanly redirects to external retailer; mandate violations block checkout with explicit reasons.

### Phase 7: Purchase History, AI Insights & Settings
- **Objectives:**
  1. Implement My Purchases view via `GET /api/checkout/history/{session_id}` with search and status filters.
  2. Implement itemized order receipt modal (`GET /api/checkout/orders/{id}`).
  3. Implement AI Insights view with spending analytics (or empty state if insufficient data).
  4. Implement Settings & Help Center explaining system mechanisms, data labeling, and sandbox environment disclosures.
- **Verification:** History accurately lists completed vs pending orders; receipts display verified capture IDs; help center documents system capabilities.

### Phase 8: Full End-to-End Testing & Verification
- **Objectives:**
  1. Verify zero critical console errors across all pages.
  2. Verify full responsive mobile layout and drawer navigation.
  3. Run full backend pytest regression suite (170/170 tests passing).
  4. Document end-to-end evidence of real sandbox checkout and external merchant redirection.
- **Verification:** All 20 acceptance criteria met; comprehensive final completion report generated.

---

## 5. Risk Assessment & Contingencies

| Identified Risk | Impact | Prevention / Mitigation |
| :--- | :--- | :--- |
| **Root Route Conflict (`GET /`)** | Frontend SPA cannot load if `GET /` is tied to `RootResponse` | Reconfigure `main.py` in Phase 2 to serve `frontend/index.html` at `/` while moving JSON root info to `/api` or `/health`. |
| **Gemini API 503 / High Demand** | AI queries fail | Assistant service already implements deterministic fallback. UI prominently indicates degraded mode and continues to display valid retrieved products. |
| **Channel3 API Rate Limit (429)** | Live search fails | UI catches HTTP 429 and offers catalog search fallback with toast explanation. |
| **Currency Mismatch in Checkout** | Buyer attempts to checkout item in unsupported currency | Backend rejects with `UnsupportedCurrencyError`. UI disables checkout for currency-mismatched items and flags them amber. |
| **Accidental State Loss on Refresh** | User loses active session | `session_identifier` is safely persisted in `localStorage`. App re-hydrates state on load. |
| **Simulated vs Real Confusion** | User believes an external order was placed internally | UI explicitly discloses simulated sandbox status for demo items and displays external merchant outbound link for Channel3 items. |

---

## 6. Phase 1 Sign-Off

Phase 1 (Audit) is complete. The architecture, API contracts, security boundaries, and implementation plan are thoroughly documented. 

Ready to proceed with Phase 2 upon user approval.
