"""
AI-Powered Multilingual Shopping Intelligence Platform
Product Catalog & Comparison Service.
Orchestrates product search, live aggregation, detail retrieval, and multi-product comparison matrices.
Enforces strict currency-safety, robust data-quality preservation, and zero fabricated scores.
"""

from math import ceil
from typing import Sequence, Any
import logging
from sqlalchemy.orm import Session

from backend.app.models.shopping import Product, RetailerOffer
from backend.app.repositories.product_repository import ProductRepository
from backend.app.schemas.product import (
    ProductResponse,
    ProductDetailResponse,
    ProductListResponse,
    ProductCompareItem,
    ProductComparisonResponse,
    RetailerOfferResponse,
)
from backend.app.services.channel3_client import Channel3Client, Channel3Error
from backend.app.services.channel3_normalizer import Channel3Normalizer

logger = logging.getLogger(__name__)


class ProductService:
    """Business logic service for product discovery, live aggregation, and multi-product comparisons."""

    @staticmethod
    def _enrich_product_response(product: Product) -> ProductResponse:
        """Helper to compute lowest price, extract ratings/warnings, and convert to ProductResponse schema."""
        lowest_price = product.lowest_price()
        offers = [RetailerOfferResponse.model_validate(o) for o in product.offers]

        specs = product.specifications or {}
        public_specs = {k: v for k, v in specs.items() if not k.startswith("_")}
        rating_val = specs.get("rating")
        rating_count = specs.get("rating_count")
        quality_warnings = list(specs.get("_data_quality_warnings", []))

        return ProductResponse(
            id=product.id,
            name=product.name,
            brand=product.brand,
            category=product.category,
            description=product.description,
            specifications=public_specs,
            image_url=product.image_url,
            is_synthetic=bool(getattr(product, "is_synthetic", True)),
            provider=str(getattr(product, "provider", "synthetic")),
            provider_product_id=getattr(product, "provider_product_id", None),
            created_at=product.created_at,
            lowest_price=lowest_price,
            offers=offers,
            rating=float(rating_val) if isinstance(rating_val, (int, float)) else None,
            rating_count=int(rating_count) if isinstance(rating_count, (int, float)) else None,
            data_quality_warnings=quality_warnings,
        )

    @staticmethod
    def search_products(
        db: Session,
        query: str | None = None,
        category: str | None = None,
        brand: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        source: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ProductListResponse:
        """Search products from stored catalog with fuzzy matching, facets, source filtering, and pagination."""
        page = max(1, page)
        page_size = max(1, min(page_size, 100))

        products, total = ProductRepository.list_products(
            db=db,
            query=query,
            category=category,
            brand=brand,
            min_price=min_price,
            max_price=max_price,
            source=source,
            page=page,
            page_size=page_size,
        )

        items = [ProductService._enrich_product_response(p) for p in products]
        total_pages = ceil(total / page_size) if total > 0 else 1

        return ProductListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @staticmethod
    def search_live_products(
        db: Session,
        query: str,
        limit: int = 10,
        client: Channel3Client | None = None,
    ) -> ProductListResponse:
        """
        Execute live product aggregation against Channel3, normalize results,
        persist/update them in the database, and return standardized product responses.
        Strictly raises provider exceptions on failure without falling back to synthetic products.
        """
        if not query or not query.strip():
            return ProductListResponse(
                items=[],
                total=0,
                page=1,
                page_size=limit,
                total_pages=1,
            )

        c3_client = client or Channel3Client()
        raw_response = c3_client.search_products(query=query.strip(), limit=limit)

        normalized_products = Channel3Normalizer.normalize_search_response(raw_response)

        persisted_products: list[Product] = []
        for norm_prod in normalized_products:
            saved = ProductRepository.upsert_channel3_product(db, norm_prod)
            persisted_products.append(saved)

        items = [ProductService._enrich_product_response(p) for p in persisted_products]

        return ProductListResponse(
            items=items,
            total=len(items),
            page=1,
            page_size=limit,
            total_pages=1,
        )

    @staticmethod
    def get_product_detail(db: Session, product_id: str) -> ProductDetailResponse | None:
        """Retrieve full product details including lowest price, best retailer, and provenance."""
        product = ProductRepository.get_by_id(db, product_id)
        if not product:
            return None

        best_offer = product.lowest_price_offer()
        lowest_price = best_offer.price if best_offer else None
        best_retailer = best_offer.retailer_name if best_offer else None

        offers = [RetailerOfferResponse.model_validate(o) for o in product.offers]

        specs = product.specifications or {}
        public_specs = {k: v for k, v in specs.items() if not k.startswith("_")}
        rating_val = specs.get("rating")
        rating_count = specs.get("rating_count")
        quality_warnings = list(specs.get("_data_quality_warnings", []))

        return ProductDetailResponse(
            id=product.id,
            name=product.name,
            brand=product.brand,
            category=product.category,
            description=product.description,
            specifications=public_specs,
            image_url=product.image_url,
            is_synthetic=bool(getattr(product, "is_synthetic", True)),
            provider=str(getattr(product, "provider", "synthetic")),
            provider_product_id=getattr(product, "provider_product_id", None),
            created_at=product.created_at,
            lowest_price=lowest_price,
            lowest_price_retailer=best_retailer,
            total_offers=len(offers),
            offers=offers,
            rating=float(rating_val) if isinstance(rating_val, (int, float)) else None,
            rating_count=int(rating_count) if isinstance(rating_count, (int, float)) else None,
            data_quality_warnings=quality_warnings,
        )

    @staticmethod
    def compare_products(db: Session, product_ids: Sequence[str]) -> ProductComparisonResponse:
        """
        Build a structured multi-product comparison matrix comparing specifications,
        retailer offers, price spreads, provenance, and overall availability.
        Enforces strict currency-safety:
        - Detects mixed currencies across products and offers (e.g. USD vs INR).
        - NEVER directly compares numeric prices across different currencies.
        - Identifies exact retailer associated with each lowest price.
        - Clearly represents missing specifications as 'Not Specified'.
        - Fabricates zero value-for-money scores.
        """
        products = ProductRepository.get_by_ids(db, product_ids)
        if not products:
            return ProductComparisonResponse(
                products=[],
                compared_count=0,
                comparison_matrix={},
                price_summary={},
            )

        compare_items: list[ProductCompareItem] = []
        all_spec_keys: set[str] = set()

        # Track currencies and priced entries across all compared products
        product_currencies: set[str] = set()
        prices_by_currency: dict[str, list[dict[str, Any]]] = {}

        for p in products:
            best_offer = p.lowest_price_offer()
            lp = best_offer.price if best_offer else None
            p_currency = best_offer.currency if best_offer else "USD"

            if best_offer and lp is not None and lp > 0:
                product_currencies.add(p_currency)
                prices_by_currency.setdefault(p_currency, []).append({
                    "product_id": p.id,
                    "product_name": p.name,
                    "price": lp,
                    "retailer": best_offer.retailer_name,
                })

            offers = [RetailerOfferResponse.model_validate(o) for o in p.offers]
            for o in p.offers:
                if o.currency:
                    product_currencies.add(o.currency.strip().upper())

            best_retailer = best_offer.retailer_name if best_offer else None

            in_stock_any = any(
                o.availability.upper() in ("IN_STOCK", "LIMITED_STOCK", "LOW_STOCK")
                for o in p.offers
            )
            overall_avail = "IN_STOCK" if in_stock_any else ("OUT_OF_STOCK" if p.offers else "UNAVAILABLE")

            specs = p.specifications or {}
            public_specs = {k: v for k, v in specs.items() if not k.startswith("_")}
            all_spec_keys.update(public_specs.keys())

            rating_val = specs.get("rating")
            rating_count = specs.get("rating_count")
            quality_warnings = list(specs.get("_data_quality_warnings", []))

            compare_items.append(
                ProductCompareItem(
                    id=p.id,
                    name=p.name,
                    brand=p.brand,
                    category=p.category,
                    image_url=p.image_url,
                    lowest_price=lp,
                    currency=p_currency,
                    specifications=public_specs,
                    offers=offers,
                    best_offer_retailer=best_retailer,
                    overall_availability=overall_avail,
                    is_synthetic=bool(getattr(p, "is_synthetic", True)),
                    provider=str(getattr(p, "provider", "synthetic")),
                    provider_product_id=getattr(p, "provider_product_id", None),
                    rating=float(rating_val) if isinstance(rating_val, (int, float)) else None,
                    rating_count=int(rating_count) if isinstance(rating_count, (int, float)) else None,
                    data_quality_warnings=quality_warnings,
                )
            )

        # Build comparison matrix: map each spec key -> {product_name: spec_value}
        # Missing values are explicitly recorded as 'Not Specified'
        comparison_matrix: dict[str, dict[str, str]] = {}
        sorted_keys = sorted(all_spec_keys)

        for key in sorted_keys:
            comparison_matrix[key] = {}
            for item in compare_items:
                val = item.specifications.get(key)
                if val is None or str(val).strip() == "":
                    comparison_matrix[key][item.name] = "Not Specified"
                else:
                    comparison_matrix[key][item.name] = str(val)

        # Build currency-safe price summary
        is_multi = len(product_currencies) > 1

        if is_multi:
            # MULTI-CURRENCY SAFEGUARD: Never compare amounts across different currencies directly without FX
            by_curr_summary: dict[str, Any] = {}
            for curr, entries in prices_by_currency.items():
                min_entry = min(entries, key=lambda x: x["price"])
                all_p = [e["price"] for e in entries]
                by_curr_summary[curr] = {
                    "cheapest_product": min_entry["product_name"],
                    "cheapest_price": min_entry["price"],
                    "cheapest_retailer": min_entry["retailer"],
                    "min_market_price": min(all_p),
                    "max_market_price": max(all_p),
                    "item_count": len(entries),
                }

            price_summary: dict[str, Any] = {
                "cheapest_product": None,
                "cheapest_price": None,
                "cheapest_retailer": None,
                "min_market_price": None,
                "max_market_price": None,
                "currency": "MIXED",
                "is_multi_currency": True,
                "warning": (
                    f"Direct cross-currency comparison disabled: products use multiple currencies "
                    f"({', '.join(sorted(product_currencies))}). FX conversion is required to rank prices across currencies."
                ),
                "by_currency": by_curr_summary,
            }
        else:
            single_currency = next(iter(product_currencies)) if product_currencies else "USD"
            entries = prices_by_currency.get(single_currency, [])
            if entries:
                cheapest_entry = min(entries, key=lambda x: x["price"])
                all_p = [e["price"] for e in entries]
                all_offers_prices = [
                    o.price for item in compare_items for o in item.offers
                    if o.price and o.price > 0 and o.currency == single_currency
                ]
                min_mkt = min(all_offers_prices) if all_offers_prices else cheapest_entry["price"]
                max_mkt = max(all_offers_prices) if all_offers_prices else cheapest_entry["price"]

                price_summary = {
                    "cheapest_product": cheapest_entry["product_name"],
                    "cheapest_price": cheapest_entry["price"],
                    "cheapest_retailer": cheapest_entry["retailer"],
                    "min_market_price": min_mkt,
                    "max_market_price": max_mkt,
                    "currency": single_currency,
                    "is_multi_currency": False,
                    "warning": None,
                    "by_currency": {
                        single_currency: {
                            "cheapest_product": cheapest_entry["product_name"],
                            "cheapest_price": cheapest_entry["price"],
                            "cheapest_retailer": cheapest_entry["retailer"],
                            "item_count": len(entries),
                        }
                    },
                }
            else:
                price_summary = {
                    "cheapest_product": None,
                    "cheapest_price": None,
                    "cheapest_retailer": None,
                    "min_market_price": None,
                    "max_market_price": None,
                    "currency": single_currency,
                    "is_multi_currency": False,
                    "warning": "No priced offers available for comparison.",
                    "by_currency": {},
                }

        return ProductComparisonResponse(
            products=compare_items,
            compared_count=len(compare_items),
            comparison_matrix=comparison_matrix,
            price_summary=price_summary,
        )

    @staticmethod
    def revalidate_offer_freshness(
        db: Session,
        product_id: str,
        retailer_name: str,
        client: Channel3Client | None = None,
    ) -> tuple[bool, str, RetailerOffer | None]:
        """
        Verify that an offer is currently valid, in stock, and fresh before checkout initiation.
        For Channel3 products, uses the free GET /v1/products/{id} endpoint to retrieve a live snapshot.
        """
        product = ProductRepository.get_by_id(db, product_id)
        if not product:
            return False, f"Product '{product_id}' not found.", None

        # Synthetic demo catalog items
        if product.is_synthetic or product.provider == "synthetic":
            matching = next((o for o in product.offers if o.retailer_name.lower() == retailer_name.lower()), None)
            if not matching:
                return False, f"Retailer '{retailer_name}' not found for product.", None
            return True, "Synthetic offer verified for local demo.", matching

        # Live Channel3 items: revalidate using provider ID
        if product.provider == "channel3" and product.provider_product_id:
            c3_client = client or Channel3Client()
            try:
                raw_prod = c3_client.get_product_by_id(product.provider_product_id)
                if not raw_prod:
                    return False, "Product is no longer available on provider catalog.", None

                norm_prod = Channel3Normalizer.normalize_product(raw_prod)
                if not norm_prod:
                    return False, "Failed to normalize fresh product snapshot.", None

                updated_prod = ProductRepository.upsert_channel3_product(db, norm_prod)
                matching = next(
                    (o for o in updated_prod.offers if o.retailer_name.lower() == retailer_name.lower()),
                    None
                )
                if not matching:
                    return False, f"Offer at '{retailer_name}' is no longer active.", None

                if matching.availability.upper() not in ("IN_STOCK", "LIMITED_STOCK", "LOW_STOCK"):
                    return False, f"Offer at '{retailer_name}' is currently {matching.availability}.", matching

                return True, "Live offer verified and in stock.", matching
            except Channel3Error as exc:
                logger.error("Offer revalidation failed for product %s: %s", product_id, exc)
                return False, f"Failed to revalidate live offer: {str(exc)}", None

        return False, "Unknown provider type.", None
