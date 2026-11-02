# AI-Powered Multilingual Shopping Intelligence Platform

> **Discover smarter. Compare deeper. Spend responsibly.**

An intelligent e-commerce aggregation and spend-control engine built for the PayPal AI Hackathon. Combines multi-retailer live catalog aggregation (Channel3), deterministic user spending mandates, and transparent product comparisons.

---

## Features

- **Live Product Aggregation:** Ingests live products and multi-merchant competitor pricing across thousands of retailers via Channel3.
- **Multi-Retailer Comparison Matrix:** Side-by-side comparison of technical specifications, prices, and availability across merchants.
- **Deterministic Spending Mandates:** Non-bypassable policy engine enforcing strict user budget ceilings, max item prices, and quantity limits.
- **RFC 9457 Problem Details:** Standardized, structured error payloads across all API endpoints.
- **SQLite WAL Architecture:** SQLite with Write-Ahead Logging (`WAL`), foreign keys enabled, and automatic schema evolution.

---

## Technology Stack

- **Backend:** Python 3.13 + FastAPI
- **ORM:** SQLAlchemy 2.0 (synchronous)
- **Database:** SQLite (WAL mode) for local development, PostgreSQL for production
- **External Aggregation:** Channel3 REST API (`POST /v1/search`, `GET /v1/products/{id}`)
- **Testing:** Pytest, pytest-asyncio, HTTPX

---

## Project Structure

```text
AI-Shopping-Intelligence-Platform/
├── backend/
│   ├── app/
│   │   ├── api/             # FastAPI route controllers (health, products, mandates)
│   │   ├── core/            # Configuration, database engine, error handlers, seeding
│   │   ├── models/          # SQLAlchemy 2.0 domain entities (Product, RetailerOffer, etc.)
│   │   ├── repositories/    # Data persistence and query encapsulation
│   │   ├── schemas/         # Pydantic v2 schemas and request/response DTOs
│   │   └── services/        # Business logic, Channel3 client, policy engine
│   ├── docs/                # Architecture and integration guides
│   └── tests/               # 48 comprehensive unit and integration tests
├── docs/                    # Authoritative system documentation
├── shopping_platform.db     # SQLite development database
├── requirements.txt         # Production and development dependencies
└── pytest.ini               # Test configuration
```

---

## Quickstart

### 1. Environment Setup

Create `.env` based on `.env.example`:

```bash
cp .env.example .env
```

Ensure `CHANNEL3_API_KEY` is configured in your `.env`.

### 2. Install Dependencies

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run Automated Tests

All tests run completely offline with mocked provider responses (0 Channel3 credits consumed):

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -v
```

### 4. Start Development Server

```powershell
.\.venv\Scripts\uvicorn.exe backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

- **Interactive Swagger Documentation:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc Documentation:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **Health Check:** [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

---

## Live Product Search API

Query live multi-retailer products from Channel3:

```http
GET /api/products/search?q=wireless+headphones&limit=10
```

Response includes live normalized products with merchant offers, original currencies, and provenance tags (`is_synthetic: false`, `provider: "channel3"`).
