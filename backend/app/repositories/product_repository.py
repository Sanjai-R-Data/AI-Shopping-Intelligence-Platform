"""
AI-Powered Multilingual Shopping Intelligence Platform
Product & Retailer Offer Repository.
Encapsulates all database query logic for catalog searching, filtering, and comparisons.
"""

from datetime import datetime, timezone
from typing import Sequence
from sqlalchemy import select, func, or_, delete
from sqlalchemy.orm import Session, joinedload

from backend.app.models.shopping import Product, RetailerOffer
from backend.app.services.channel3_normalizer import NormalizedProduct


class ProductRepository:
    """Repository handling Product and RetailerOffer persistence and queries."""

    @staticmethod
    def get_by_id(db: Session, product_id: str) -> Product | None:
        """Fetch a single product by ID including all associated retailer offers."""
        stmt = (
            select(Product)
            .options(joinedload(Product.offers))
            .where(Product.id == product_id)
        )
        return db.scalars(stmt).unique().first()

    @staticmethod
    def get_by_provider_id(db: Session, provider: str, provider_product_id: str) -> Product | None:
        """Fetch a single product by provider and provider-assigned identifier."""
        stmt = (
            select(Product)
            .options(joinedload(Product.offers))
            .where(Product.provider == provider, Product.provider_product_id == provider_product_id)
        )
        return db.scalars(stmt).unique().first()

    @staticmethod
    def get_by_ids(db: Session, product_ids: Sequence[str]) -> list[Product]:
        """Fetch multiple products by IDs including their retailer offers."""
        if not product_ids:
            return []
        stmt = (
            select(Product)
            .options(joinedload(Product.offers))
            .where(Product.id.in_(product_ids))
        )
        return list(db.scalars(stmt).unique().all())

    @staticmethod
    def list_products(
        db: Session,
        query: str | None = None,
        category: str | None = None,
        brand: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        source: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Product], int]:
        """
        Search and filter products with pagination.
        Supports fuzzy name/description matching, category/brand equality, and price range filtering.
        Optionally filters by source: 'synthetic', 'live' / 'channel3', or all.
        """
        stmt = select(Product).options(joinedload(Product.offers))
        count_stmt = select(func.count(Product.id))

        filters = []
        if query:
            clean_q = f"%{query.strip()}%"
            filters.append(
                or_(
                    Product.name.ilike(clean_q),
                    Product.description.ilike(clean_q),
                    Product.brand.ilike(clean_q),
                )
            )

        if category:
            filters.append(Product.category.ilike(category.strip()))

        if brand:
            filters.append(Product.brand.ilike(brand.strip()))

        if min_price is not None:
            filters.append(Product.offers.any(RetailerOffer.price >= min_price))

        if max_price is not None:
            filters.append(Product.offers.any(RetailerOffer.price <= max_price))

        if source:
            source_lower = source.strip().lower()
            if source_lower == "synthetic":
                filters.append(Product.is_synthetic == True)
            elif source_lower in ("live", "channel3"):
                filters.append(Product.is_synthetic == False)

        if filters:
            stmt = stmt.where(*filters)
            count_stmt = count_stmt.where(*filters)

        # Total count before pagination
        total = db.scalar(count_stmt) or 0

        # Pagination ordering by product name
        offset = max(0, (page - 1) * page_size)
        stmt = stmt.order_by(Product.name.asc()).offset(offset).limit(page_size)

        products = list(db.scalars(stmt).unique().all())
        return products, total

    @staticmethod
    def upsert_channel3_product(db: Session, norm: NormalizedProduct) -> Product:
        """
        Persist or update a normalized Channel3 product and its competing offers.
        Prevents duplicate entries on repeated searches and refreshes offer prices/freshness.
        """
        existing = ProductRepository.get_by_provider_id(
            db, provider="channel3", provider_product_id=norm.provider_product_id
        )

        now_utc = datetime.now(timezone.utc)

        if existing:
            # Update product details
            existing.name = norm.name
            existing.brand = norm.brand
            existing.category = norm.category
            existing.description = norm.description
            existing.specifications = norm.specifications
            if norm.image_url:
                existing.image_url = norm.image_url
            existing.updated_at = now_utc

            # Refresh retailer offers: clear existing and re-attach fresh offers
            existing.offers.clear()
            for offer in norm.offers:
                ro = RetailerOffer(
                    product_id=existing.id,
                    retailer_name=offer.retailer_name,
                    price=offer.price,
                    currency=offer.currency,
                    product_url=offer.product_url,
                    availability=offer.availability,
                    compare_at_price=offer.compare_at_price,
                    provider_offer_id=offer.provider_offer_id,
                    is_synthetic=False,
                    retrieved_at=offer.retrieved_at or now_utc,
                )
                existing.offers.append(ro)

            db.commit()
            db.refresh(existing)
            return existing

        # Create new product
        new_prod = Product(
            name=norm.name,
            brand=norm.brand,
            category=norm.category,
            description=norm.description,
            specifications=norm.specifications,
            image_url=norm.image_url,
            provider="channel3",
            provider_product_id=norm.provider_product_id,
            is_synthetic=False,
            created_at=now_utc,
            updated_at=now_utc,
        )

        for offer in norm.offers:
            ro = RetailerOffer(
                retailer_name=offer.retailer_name,
                price=offer.price,
                currency=offer.currency,
                product_url=offer.product_url,
                availability=offer.availability,
                compare_at_price=offer.compare_at_price,
                provider_offer_id=offer.provider_offer_id,
                is_synthetic=False,
                retrieved_at=offer.retrieved_at or now_utc,
            )
            new_prod.offers.append(ro)

        db.add(new_prod)
        db.commit()
        db.refresh(new_prod)
        return new_prod

    @staticmethod
    def create(db: Session, product: Product) -> Product:
        """Persist a new product record."""
        db.add(product)
        db.commit()
        db.refresh(product)
        return product

    @staticmethod
    def count(db: Session) -> int:
        """Return total count of products in the catalog."""
        return db.scalar(select(func.count(Product.id))) or 0
