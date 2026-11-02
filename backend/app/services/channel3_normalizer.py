"""
AI-Powered Multilingual Shopping Intelligence Platform
Channel3 Product & Offer Normalizer.
Converts raw Channel3 API JSON payloads into clean, canonical data structures
aligned with the Product and RetailerOffer domain models.
Enforces rigorous data quality validation: numeric ratings, taxonomy conflict
detection, brand consistency checks, and transparent provenance tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Known primary consumer hardware and audio brands for mismatch heuristics
RECOGNIZED_BRANDS = [
    "Anker", "Soundcore", "Sony", "Apple", "Samsung", "Sennheiser",
    "Bose", "JVC", "JBL", "LG", "Philips", "Beats", "Google",
    "Microsoft", "Logitech", "Garmin", "Fitbit", "Skullcandy", "Audio-Technica"
]


@dataclass
class NormalizedOffer:
    """Normalized retailer offer data extracted from Channel3."""
    retailer_name: str
    price: float
    currency: str
    product_url: str
    availability: str
    compare_at_price: float | None = None
    provider_offer_id: str | None = None
    is_synthetic: bool = False
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class NormalizedProduct:
    """Normalized product metadata and specifications extracted from Channel3."""
    name: str
    brand: str
    category: str
    description: str
    specifications: dict[str, Any]
    image_url: str | None
    provider: str
    provider_product_id: str
    is_synthetic: bool
    offers: list[NormalizedOffer] = field(default_factory=list)
    rating: float | None = None
    rating_count: int | None = None
    data_quality_warnings: list[str] = field(default_factory=list)


class Channel3Normalizer:
    """
    Normalizes Channel3 API products and retailer offers.
    Adheres to strict data integrity:
    - Preserves original currency and retailer URLs verbatim.
    - Represents ratings using consistent validated numeric types (0.0 to 5.0 float).
    - Detects and documents upstream data inconsistencies (brand mismatches, taxonomy discrepancies).
    - Preserves provider data without inventing or fabricating missing specifications.
    """

    @staticmethod
    def _parse_rating(raw_ratings: Any) -> tuple[float | None, int | None]:
        """
        Extract and validate numeric rating score and review count.
        Ensures ratings are strictly represented as valid floats between 0.0 and 5.0.
        Invalid, out-of-bounds, or non-numeric values are safely returned as None.
        """
        if not isinstance(raw_ratings, dict):
            return None, None

        parsed_val: float | None = None
        raw_val = raw_ratings.get("value")
        if raw_val is not None:
            try:
                num = float(raw_val)
                if 0.0 <= num <= 5.0:
                    parsed_val = round(num, 2)
                elif 5.0 < num <= 10.0:
                    # Normalize 10-point scale down to 5.0 scale
                    parsed_val = round(num / 2.0, 2)
                else:
                    logger.warning("Rating value %.2f out of plausible range [0, 5]; omitting", num)
            except (ValueError, TypeError):
                logger.warning("Non-numeric rating value '%s' encountered; omitting", raw_val)

        parsed_count: int | None = None
        raw_count = raw_ratings.get("count")
        if raw_count is not None:
            try:
                cnt = int(raw_count)
                if cnt >= 0:
                    parsed_count = cnt
            except (ValueError, TypeError):
                pass

        return parsed_val, parsed_count

    @staticmethod
    def _detect_data_quality_issues(
        title: str,
        brand: str,
        category: str,
        specs: dict[str, Any],
        description: str,
    ) -> list[str]:
        """
        Audit raw product data for upstream inconsistencies without mutating source fields.
        Returns a list of human-readable data quality warnings.
        """
        warnings: list[str] = []

        # 1. Brand Inconsistency: Title prominently mentions a recognized brand that differs from provider brand
        title_lower = title.lower()
        brand_lower = brand.lower()
        for rec_brand in RECOGNIZED_BRANDS:
            rec_lower = rec_brand.lower()
            pattern = rf"\b{re.escape(rec_lower)}\b"
            if re.search(pattern, title_lower) and rec_lower not in brand_lower:
                warnings.append(
                    f"Brand discrepancy: title mentions '{rec_brand}' but provider assigned brand is '{brand}'."
                )
                break

        # 2. Taxonomy Contradiction: Category conflicts with headphone style specification
        cat_lower = category.lower()
        style_spec = str(specs.get("headphone-style") or "").lower()
        if "over-ear" in cat_lower or "on-ear" in cat_lower:
            if "ear hooks" in style_spec or "in-ear" in style_spec or "canal" in style_spec:
                warnings.append(
                    f"Taxonomy discrepancy: category is '{category}' but headphone-style specification is '{specs.get('headphone-style')}'."
                )

        # 3. Model Identifier Discrepancy: Title model variant suffix differs from description
        title_tokens = set(re.findall(r"\b[A-Za-z0-9-]{5,15}\b", title))
        desc_tokens = set(re.findall(r"\b[A-Za-z0-9-]{5,15}\b", description))
        for token in title_tokens:
            if any(c.isdigit() for c in token) and len(token) >= 6:
                base = token[:-1]  # Check if model family without variant suffix is used in description
                if base in desc_tokens and token not in desc_tokens:
                    warnings.append(
                        f"Model variant discrepancy: title specifies variant '{token}' while description references base model '{base}'."
                    )
                    break

        return warnings

    @classmethod
    def normalize_product(cls, raw: dict[str, Any]) -> NormalizedProduct | None:
        """
        Transform a single raw product item from Channel3 into a NormalizedProduct.
        Returns None if product has no valid identifier or title.
        """
        if not isinstance(raw, dict):
            return None

        raw_id = raw.get("id")
        if not raw_id:
            logger.warning("Skipping Channel3 product with missing 'id'")
            return None

        title = raw.get("title") or raw.get("name")
        if not title or not str(title).strip():
            logger.warning("Skipping Channel3 product '%s' with empty title", raw_id)
            return None

        # 1. Brand extraction: Preserve provider brand verbatim
        brands = raw.get("brands")
        brand_name = "Unknown"
        if isinstance(brands, list) and brands:
            first_b = brands[0]
            if isinstance(first_b, dict) and first_b.get("name"):
                brand_name = str(first_b["name"]).strip()
            elif isinstance(first_b, str):
                brand_name = first_b.strip()
        elif isinstance(raw.get("brand"), str):
            brand_name = raw["brand"].strip()

        # 2. Category extraction
        cat = raw.get("category")
        category_name = "General"
        if isinstance(cat, dict):
            category_name = cat.get("title") or cat.get("slug") or "General"
        elif isinstance(cat, str) and cat.strip():
            category_name = cat.strip()

        # 3. Description: Preserved faithfully including special characters
        description = str(raw.get("description") or "").strip()

        # 4. Image URL extraction (prefers cleaned_url or hero/is_main_image)
        image_url = None
        images = raw.get("images")
        if isinstance(images, list) and images:
            main_img = next((img for img in images if isinstance(img, dict) and img.get("is_main_image")), None)
            if not main_img and isinstance(images[0], dict):
                main_img = images[0]
            if main_img and isinstance(main_img, dict):
                image_url = main_img.get("cleaned_url") or main_img.get("url") or main_img.get("thumbnail_url")

        # 5. Specifications & Attributes extraction
        specs: dict[str, Any] = {}
        structured_attrs = raw.get("structured_attributes")
        if isinstance(structured_attrs, dict):
            for k, v in structured_attrs.items():
                if isinstance(v, list):
                    specs[k] = ", ".join(str(x) for x in v)
                elif v is not None:
                    specs[k] = str(v)

        key_features = raw.get("key_features")
        if isinstance(key_features, list) and key_features:
            specs["key_features"] = [str(f) for f in key_features if f]

        materials = raw.get("materials")
        if isinstance(materials, list) and materials:
            specs["materials"] = ", ".join(str(m) for m in materials if m)

        # 6. Validated Numeric Rating Handling (Fix for Issue 4: stringified ratings)
        rating_val, rating_count = cls._parse_rating(raw.get("ratings"))
        if rating_val is not None:
            specs["rating"] = rating_val
        if rating_count is not None:
            specs["rating_count"] = rating_count

        # 7. Data Quality Audit & Warnings
        warnings = cls._detect_data_quality_issues(
            title=str(title).strip(),
            brand=brand_name,
            category=category_name,
            specs=specs,
            description=description,
        )
        if warnings:
            specs["_data_quality_warnings"] = warnings

        now_utc = datetime.now(timezone.utc)

        # 8. Retailer offers normalization
        normalized_offers: list[NormalizedOffer] = []
        raw_offers = raw.get("offers")
        if isinstance(raw_offers, list):
            for o in raw_offers:
                if not isinstance(o, dict):
                    continue

                price_info = o.get("price")
                if not isinstance(price_info, dict):
                    continue

                price_val = price_info.get("price")
                if price_val is None or not isinstance(price_val, (int, float)) or price_val <= 0:
                    continue  # Missing or invalid prices are omitted (never set to zero)

                currency = str(price_info.get("currency") or "USD").strip().upper()
                compare_at = price_info.get("compare_at_price")
                compare_at_val = (
                    float(compare_at)
                    if isinstance(compare_at, (int, float)) and compare_at > float(price_val)
                    else None
                )

                domain = str(o.get("domain") or "Marketplace").strip()
                outbound_url = str(o.get("url") or f"https://{domain}").strip()

                # Normalize availability
                avail_raw = str(o.get("availability") or "InStock").strip()
                if "instock" in avail_raw.lower():
                    avail_norm = "IN_STOCK"
                elif "outofstock" in avail_raw.lower():
                    avail_norm = "OUT_OF_STOCK"
                elif "limited" in avail_raw.lower() or "low" in avail_raw.lower():
                    avail_norm = "LIMITED_STOCK"
                else:
                    avail_norm = avail_raw.upper()

                offer_id = o.get("id") or f"{raw_id}-{domain}"

                normalized_offers.append(
                    NormalizedOffer(
                        retailer_name=domain,
                        price=float(price_val),
                        currency=currency,
                        product_url=outbound_url,
                        availability=avail_norm,
                        compare_at_price=compare_at_val,
                        provider_offer_id=str(offer_id),
                        is_synthetic=False,
                        retrieved_at=now_utc,
                    )
                )

        return NormalizedProduct(
            name=str(title).strip(),
            brand=brand_name,
            category=category_name,
            description=description,
            specifications=specs,
            image_url=image_url,
            provider="channel3",
            provider_product_id=str(raw_id),
            is_synthetic=False,
            offers=normalized_offers,
            rating=rating_val,
            rating_count=rating_count,
            data_quality_warnings=warnings,
        )

    @classmethod
    def normalize_search_response(cls, response_data: dict[str, Any]) -> list[NormalizedProduct]:
        """Normalize all products returned by a Channel3 search response."""
        if not isinstance(response_data, dict):
            return []

        products_raw = response_data.get("products")
        if not isinstance(products_raw, list):
            return []

        results: list[NormalizedProduct] = []
        for raw_item in products_raw:
            norm = cls.normalize_product(raw_item)
            if norm:
                results.append(norm)

        return results
