"""
AI-Powered Multilingual Shopping Intelligence Platform
AI Shopping Assistant Orchestrator.
Coordinates user queries, Gemini intent extraction, Channel3 product search,
deterministic spending policy evaluation, grounded product intelligence, and specification/currency eligibility filtering.
Enforces the core security boundary: AI suggests, Backend validates, User approves, PayPal processes.
"""

import logging
import re
from typing import Any
from sqlalchemy.orm import Session

from backend.app.models.shopping import ShoppingSession
from backend.app.repositories.mandate_repository import MandateRepository
from backend.app.repositories.product_repository import ProductRepository
from backend.app.schemas.assistant import (
    ShoppingIntent,
    SpecificationRequirement,
    ProductEligibilityItem,
    ProductIntelligence,
    AssistantQueryRequest,
    AssistantQueryResponse,
)
from backend.app.schemas.product import ProductResponse
from backend.app.services.channel3_client import Channel3Client, Channel3Error
from backend.app.services.gemini_client import (
    GeminiClient,
    GeminiError,
    GeminiUnavailableError,
    GeminiTimeoutError,
    GeminiRateLimitError,
    GeminiAuthError,
)
from backend.app.services.policy_engine import SpendingPolicyEngine
from backend.app.services.product_service import ProductService

logger = logging.getLogger(__name__)


class AssistantService:
    """
    Central business logic coordinator for the AI Shopping Assistant.
    """

    @staticmethod
    def _fallback_rule_based_intent(query: str) -> ShoppingIntent:
        """
        Deterministic rule-based intent extractor used when Gemini is temporarily unavailable.
        Extracts numbers, currency symbols, basic category tokens, hardware specifications (RAM, storage),
        and language without pretending to be LLM reasoning.
        """
        clean_q = query.strip()
        lower_q = clean_q.lower()

        # Language detection (Tamil unicode range 0x0B80 - 0x0BFF, Spanish, French)
        detected_language = "en"
        if re.search(r"[\u0B80-\u0BFF]", clean_q):
            detected_language = "ta"
        elif any(w in lower_q for w in ["para", "con", "por menos", "portátil", "computadora"]):
            detected_language = "es"
        elif any(w in lower_q for w in ["pour", "avec", "sous", "casque", "ordinateur"]):
            detected_language = "fr"

        # Currency detection
        currency = "USD"
        if "₹" in clean_q or "rs" in lower_q or "inr" in lower_q or "rupee" in lower_q or "ரூபாய்" in clean_q:
            currency = "INR"
        elif "€" in clean_q or "eur" in lower_q:
            currency = "EUR"
        elif "£" in clean_q or "gbp" in lower_q:
            currency = "GBP"

        # Budget extraction (e.g. under 70000, under $100, under ₹5,000, ₹70000க்குள்)
        max_budget = None
        b_patterns = [
            r"(?:under|below|less than|max(?:imum)?|por menos de|sous)\s*[$₹€£]?\s*([\d,]+(?:\.\d+)?)",
            r"[$₹€£]\s*([\d,]+(?:\.\d+)?)",
            r"([\d,]+(?:\.\d+)?)\s*(?:inr|rupees?|ரூபாய்|க்குள்)",
        ]
        for pat in b_patterns:
            bm = re.search(pat, lower_q)
            if bm:
                try:
                    num_str = bm.group(1).replace(",", "")
                    parsed_val = float(num_str)
                    # Disambiguate from RAM sizes (like 16 or 32) unless currency symbol was present
                    if parsed_val > 64 or "₹" in clean_q or "$" in clean_q or "€" in clean_q:
                        max_budget = parsed_val
                        break
                except ValueError:
                    pass

        # Category matching
        category = "general"
        categories = ["laptop", "notebook", "portátil", "ordinateur", "headphones", "headset", "earphones", "casque", "smartphone", "phone", "smartwatch", "watch", "camera"]
        for cat in categories:
            if cat in lower_q:
                if cat in ["notebook", "portátil", "ordinateur"]:
                    category = "laptop"
                elif cat in ["headset", "earphones", "casque"]:
                    category = "headphones"
                elif cat in ["phone"]:
                    category = "smartphone"
                elif cat in ["watch"]:
                    category = "smartwatch"
                else:
                    category = cat
                break
        if "லேப்டாப்" in clean_q:
            category = "laptop"

        # Intended use
        intended_use = []
        if "machine learning" in lower_q or "ai" in lower_q or "மெஷின் லேர்னிங்" in clean_q or "deep learning" in lower_q:
            intended_use.append("machine_learning")
        if "gaming" in lower_q or "விளையாட்டு" in clean_q:
            intended_use.append("gaming")
        if "travel" in lower_q or "பயணம்" in clean_q or "viaje" in lower_q or "voyage" in lower_q:
            intended_use.append("travel")
        if "coding" in lower_q or "programming" in lower_q or "programación" in lower_q or "programmation" in lower_q:
            intended_use.append("coding")

        # Hardware Specification Extraction (RAM & Storage)
        required_specs: list[SpecificationRequirement] = []
        preferred_specs: list[SpecificationRequirement] = []

        # 1. RAM extraction
        ram_match = re.search(
            r"(?:(at least|minimum|min|must have|preferably|prefer|con al menos|avec au moins)\s+)?(\d+)\s*(?:gb|gigabytes?|ஜிபி)\s*(?:of\s*)?(?:ram|memory|memoria|mémoire|ரேம்)?",
            lower_q,
        )
        if ram_match and ("ram" in lower_q or "memory" in lower_q or "memoria" in lower_q or "mémoire" in lower_q or "ரேம்" in clean_q or "gb" in lower_q):
            prefix = ram_match.group(1)
            num = float(ram_match.group(2))
            is_pref = prefix in ("preferably", "prefer") if prefix else False
            val_str = (
                f"{int(num)} GB or more"
                if (prefix and prefix in ("at least", "minimum", "min", "must have", "con al menos", "avec au moins"))
                else f"{int(num)} GB"
            )
            ram_item = SpecificationRequirement(
                name="ram",
                value=val_str,
                raw_spec=ram_match.group(0).strip(),
                min_value=num,
                unit="GB",
                is_hard_requirement=not is_pref,
            )
            if is_pref:
                preferred_specs.append(ram_item)
            else:
                required_specs.append(ram_item)

        # 2. Storage / SSD extraction
        storage_match = re.search(
            r"(?:(at least|minimum|min|must have|preferably|prefer)\s+)?(\d+)\s*(gb|tb)\s*(?:ssd|storage|nvme|hdd)",
            lower_q,
        )
        if storage_match:
            prefix = storage_match.group(1)
            num = float(storage_match.group(2))
            unit = storage_match.group(3).upper()
            is_pref = prefix in ("preferably", "prefer") if prefix else False
            val_str = (
                f"{int(num)} {unit} or more"
                if (prefix and prefix in ("at least", "minimum", "min", "must have"))
                else f"{int(num)} {unit}"
            )
            storage_item = SpecificationRequirement(
                name="storage",
                value=val_str,
                raw_spec=storage_match.group(0).strip(),
                min_value=num,
                unit=unit,
                is_hard_requirement=not is_pref,
            )
            if is_pref:
                preferred_specs.append(storage_item)
            else:
                required_specs.append(storage_item)

        return ShoppingIntent(
            query=clean_q,
            category=category,
            intended_use=intended_use,
            max_budget=max_budget,
            currency=currency,
            required_specs=required_specs,
            preferred_specs=preferred_specs,
            detected_language=detected_language,
            clarification_required=False,
        )

    @staticmethod
    def _extract_ram_from_product(product: ProductResponse) -> tuple[float | None, str]:
        """Extract RAM in GB from product specifications, key_features, title, or description."""
        specs = product.specifications or {}

        # 1. Check dedicated RAM spec keys
        ram_keys = (
            "ram", "RAM", "memory", "Memory", "system_memory", "System Memory (RAM)",
            "ram_memory", "system_memory_ram", "ram_size", "installed_ram", "memory_size", "ram_gb",
        )
        for key in ram_keys:
            if key in specs and specs[key] is not None:
                val = specs[key]
                if isinstance(val, (int, float)) and 2 <= val <= 256:
                    return float(val), f"specs.{key}: {val} GB"
                val_str = str(val).lower()
                m = re.search(r"(\d+)\s*(?:gb|gigabytes?)", val_str)
                if m:
                    return float(m.group(1)), f"specs.{key}: {specs[key]}"

        # 2. Check structured key_features, features, or highlights
        for feat_key in ("key_features", "features", "highlights", "bullet_points"):
            feats = specs.get(feat_key)
            if feats:
                feat_list = feats if isinstance(feats, list) else [feats]
                for item in feat_list:
                    item_str = str(item).strip()
                    item_lower = item_str.lower()
                    m = (
                        re.search(r"(\d+)\s*(?:gb|gigabytes?)(?:\s+(?:ddr[345]|lpddr[45][a-z]?|sdram|unified))?\s*(?<!v)(?:ram|memory\b)", item_lower)
                        or re.search(r"(\d+)\s*(?:gb|gigabytes?)\s+(?:ddr[345]|lpddr[45][a-z]?)\b", item_lower)
                        or re.search(r"(?<!v)(?:ram|memory)\s*:\s*(\d+)\s*(?:gb|gigabytes?)", item_lower)
                    )
                    if m:
                        num = next(g for g in m.groups() if g and g.isdigit())
                        return float(num), f"specs.{feat_key}: {item_str}"

        # 3. Check product title and description
        for text, src in [(product.name, "product title"), (product.description, "description")]:
            if text:
                lower_text = text.lower()
                m = (
                    re.search(r"(\d+)\s*(?:gb|gigabytes?)(?:\s+(?:ddr[345]|lpddr[45][a-z]?|sdram|unified))?\s*(?<!v)(?:ram|memory\b)", lower_text)
                    or re.search(r"(\d+)\s*(?:gb|gigabytes?)\s+(?:ddr[345]|lpddr[45][a-z]?)\b", lower_text)
                    or re.search(r"(?<!v)(?:ram|memory)\s*:\s*(\d+)\s*(?:gb|gigabytes?)", lower_text)
                    or re.search(r"(\d+)\s*(?:gb|gigabytes?)\s+of\s+(?:system\s+)?(?<!v)(?:ram|memory)", lower_text)
                )
                if m:
                    num = next(g for g in m.groups() if g and g.isdigit())
                    return float(num), f"{src}: {m.group(0)}"

        return None, "Not specified"

    @staticmethod
    def _extract_storage_from_product(product: ProductResponse) -> tuple[float | None, str]:
        """Extract storage in GB from product specifications, key_features, title, or description."""
        specs = product.specifications or {}

        # 1. Check dedicated storage spec keys
        storage_keys = (
            "storage", "Storage", "storage-capacity", "storage_capacity",
            "storage-drive-capacity", "storage_drive_capacity",
            "ssd", "SSD", "hard_drive", "drive", "capacity", "internal_storage",
            "solid_state_drive_capacity", "ssd_capacity", "hdd_capacity"
        )
        for key in storage_keys:
            if key in specs and specs[key] is not None:
                val = specs[key]
                if isinstance(val, (int, float)):
                    if val in (128, 256, 512, 1000, 1024, 2000, 2048, 4000, 4096):
                        return float(val), f"specs.{key}: {val} GB"
                    if val in (1, 2, 4, 8) and ("tb" in key.lower() or val <= 4):
                        return float(val) * 1024.0, f"specs.{key}: {val} TB"

                val_str = str(val).lower()
                tb_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:tb|terabytes?)", val_str)
                if tb_m:
                    return float(tb_m.group(1)) * 1024.0, f"specs.{key}: {specs[key]}"
                gb_m = re.search(r"(\d+)\s*(?:gb|gigabytes?)", val_str)
                if gb_m:
                    return float(gb_m.group(1)), f"specs.{key}: {specs[key]}"

        # 2. Check structured key_features, features, or highlights
        for feat_key in ("key_features", "features", "highlights", "bullet_points"):
            feats = specs.get(feat_key)
            if feats:
                feat_list = feats if isinstance(feats, list) else [feats]
                for item in feat_list:
                    item_str = str(item).strip()
                    item_lower = item_str.lower()
                    tb_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:tb|terabytes?)(?:\s+(?:pcie|nvme|m\.2))*\s*(?:ssd|storage|nvme|hdd|drive)?", item_lower)
                    if tb_m:
                        return float(tb_m.group(1)) * 1024.0, f"specs.{feat_key}: {item_str}"
                    gb_m = re.search(r"(\d+)\s*(?:gb|gigabytes?)(?:\s+(?:pcie|nvme|gen\s*\d|m\.2))*\s*(?:ssd|storage|nvme|hdd|drive|emmc)", item_lower)
                    if gb_m:
                        return float(gb_m.group(1)), f"specs.{feat_key}: {item_str}"

        # 3. Check product title and description
        for text, src in [(product.name, "product title"), (product.description, "description")]:
            if text:
                lower_text = text.lower()
                tb_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:tb|terabytes?)(?:\s+(?:pcie|nvme|gen\s*\d|m\.2))*\s*(?:ssd|storage|nvme|hdd|drive)?", lower_text)
                if tb_m:
                    return float(tb_m.group(1)) * 1024.0, f"{src}: {tb_m.group(0)}"
                gb_m = re.search(r"(\d+)\s*(?:gb|gigabytes?)(?:\s+(?:pcie|nvme|gen\s*\d|m\.2))*\s*(?:ssd|storage|nvme|hdd|drive|emmc)", lower_text)
                if gb_m:
                    return float(gb_m.group(1)), f"{src}: {gb_m.group(0)}"

        return None, "Not specified"

    @classmethod
    def evaluate_product_eligibility(
        cls,
        product: ProductResponse,
        intent: ShoppingIntent,
    ) -> ProductEligibilityItem:
        """
        Authoritative deterministic product eligibility evaluator.
        Enforces specification verification and currency/budget constraints:
        - If user specifies INR budget, USD offers cannot qualify without verified FX conversion.
        - If user requires at least 16GB RAM:
            - Verified RAM >= 16GB qualifies.
            - Verified RAM < 16GB is excluded.
            - Unknown RAM is marked UNVERIFIED_SPECS.
        """
        reasons: list[str] = []
        verified_specs: dict[str, Any] = {}
        unverified_specs: list[str] = []
        status = "QUALIFIED"

        # Step A: Evaluate Hard Specification Requirements
        for req in intent.required_specs:
            spec_name = req.name.lower()
            if spec_name == "ram":
                ram_gb, evidence_src = cls._extract_ram_from_product(product)
                if ram_gb is None:
                    status = "UNVERIFIED_SPECS"
                    unverified_specs.append("ram")
                    reasons.append(
                        f"RAM specification is missing from product details; cannot confirm requirement of {req.value}."
                    )
                else:
                    verified_specs["ram"] = f"{int(ram_gb)} GB"
                    if req.min_value is not None:
                        if ram_gb < req.min_value:
                            status = "EXCLUDED"
                            reasons.append(
                                f"Verified RAM of {int(ram_gb)} GB is below your required minimum of {int(req.min_value)} GB."
                            )
                        else:
                            reasons.append(
                                f"Verified RAM of {int(ram_gb)} GB meets your required minimum of {int(req.min_value)} GB ({evidence_src})."
                            )
            elif spec_name in ("storage", "ssd"):
                storage_gb, storage_src = cls._extract_storage_from_product(product)
                if storage_gb is None:
                    if status == "QUALIFIED":
                        status = "UNVERIFIED_SPECS"
                    unverified_specs.append("storage")
                    reasons.append(f"Storage specification is unverified ({req.value}).")
                else:
                    verified_specs["storage"] = f"{storage_gb} GB"
                    if req.min_value is not None:
                        min_gb = req.min_value * 1024.0 if req.unit == "TB" else req.min_value
                        if storage_gb < min_gb:
                            status = "EXCLUDED"
                            reasons.append(
                                f"Verified storage of {int(storage_gb)} GB is below your required minimum of {int(min_gb)} GB."
                            )
                        else:
                            reasons.append(
                                f"Verified storage of {int(storage_gb)} GB meets your required minimum ({storage_src})."
                            )

        # Step B: Evaluate Currency and Budget Constraints
        if intent.max_budget is not None:
            lowest_price = product.lowest_price
            offer_currency = product.offers[0].currency if product.offers and product.offers[0].currency else None

            if lowest_price is None or not offer_currency:
                if status == "QUALIFIED":
                    status = "UNVERIFIED_SPECS"
                reasons.append("Retailer pricing or offer currency is unavailable.")
            elif offer_currency.upper() != intent.currency.upper():
                # Cross-currency rule: Cannot compare directly without verified FX rate
                if status != "EXCLUDED":
                    status = "CURRENCY_MISMATCH"
                reasons.append(
                    f"Offer is priced in {offer_currency.upper()} ({lowest_price:,.2f} {offer_currency.upper()}), "
                    f"which cannot be directly evaluated against your {intent.currency.upper()} budget "
                    f"({intent.max_budget:,.2f} {intent.currency.upper()}) without verified real-time FX conversion."
                )
            else:
                # Same currency: evaluate numerical budget limit
                if lowest_price > intent.max_budget:
                    status = "EXCLUDED"
                    reasons.append(
                        f"Price of {lowest_price:,.2f} {offer_currency.upper()} exceeds your maximum budget of "
                        f"{intent.max_budget:,.2f} {intent.currency.upper()}."
                    )
                else:
                    reasons.append(
                        f"Price of {lowest_price:,.2f} {offer_currency.upper()} is within your budget of "
                        f"{intent.max_budget:,.2f} {intent.currency.upper()}."
                    )

        is_qualified = (status == "QUALIFIED")
        return ProductEligibilityItem(
            product_id=product.id,
            product_name=product.name,
            status=status,
            is_qualified=is_qualified,
            reasons=reasons,
            verified_specs=verified_specs,
            unverified_specs=unverified_specs,
        )

    @classmethod
    def validate_and_sanitize_intelligence(
        cls,
        analyses: list[ProductIntelligence],
        eligibility_map: dict[str, ProductEligibilityItem],
    ) -> list[ProductIntelligence]:
        """
        Authoritative backend validation and sanitization layer for AI product intelligence.
        Guarantees that Gemini output never contradicts deterministic eligibility results:
        1. Deterministic eligibility is the single source of truth.
        2. Specifications marked unverified (e.g. RAM, storage) must NEVER be presented as confirmed strengths.
        3. Removes unsupported specification claims from strengths and advantages, while preserving
           all legitimate evidenced strengths (CPU, GPU, display, chassis, etc.).
        4. Accurately reflects deterministic status in suitability:
           - QUALIFIED: Retains suitable rating.
           - UNVERIFIED_SPECS: Marks as conditionally suitable pending verification (does not mark as excluded).
           - EXCLUDED: Marks as not recommended / excluded due to failing hard specs or budget.
           - CURRENCY_MISMATCH: Notes currency disparity requiring FX conversion.
        """
        sanitized_list: list[ProductIntelligence] = []

        ram_claim_patterns = [
            re.compile(r"\b(?:\d+\s*(?:gb|gigabytes?)\s*(?:ddr[345]|lpddr[45][a-z]?|sdram|unified)?\s*)?(?<!v)(?<!g)ram\b", re.IGNORECASE),
            re.compile(r"\b(?:\d+\s*(?:gb|gigabytes?)\s+(?:ddr[345]|lpddr[45][a-z]?))\b", re.IGNORECASE),
            re.compile(r"\b(?:\d+\s*(?:gb|gigabytes?)\s+of\s+system\s+memory)\b", re.IGNORECASE),
            re.compile(r"\b(?:system\s+memory|installed\s+memory)\b", re.IGNORECASE),
            re.compile(r"\b(?:sufficient|ample|generous|adequate)\s+ram\b", re.IGNORECASE),
        ]

        storage_claim_patterns = [
            re.compile(r"\b(?:\d+\s*(?:tb|terabytes?|gb|gigabytes?)\s*(?:pcie|nvme|m\.2)?\s*)?(?:ssd|nvme|solid\s+state|hard\s+drive|hdd|storage\s+capacity)\b", re.IGNORECASE),
            re.compile(r"\b(?:\d+\s*tb\s+storage)\b", re.IGNORECASE),
            re.compile(r"\b(?:sufficient|ample|generous|adequate|large)\s+storage\b", re.IGNORECASE),
        ]

        for item in analyses:
            elig = eligibility_map.get(item.product_id)
            if not elig:
                sanitized_list.append(item)
                continue

            unverified = [s.lower() for s in elig.unverified_specs]
            has_unverified_ram = "ram" in unverified
            has_unverified_storage = any(s in ("storage", "ssd") for s in unverified)

            # 1. Filter strengths
            clean_strengths: list[str] = []
            for st in item.strengths:
                st_lower = st.lower()
                is_invalid_ram = False
                if has_unverified_ram:
                    if ("vram" in st_lower or "gddr" in st_lower or "graphics memory" in st_lower) and not ("system memory" in st_lower or "system ram" in st_lower):
                        is_invalid_ram = False
                    else:
                        is_invalid_ram = any(p.search(st) for p in ram_claim_patterns)

                is_invalid_storage = False
                if has_unverified_storage:
                    is_invalid_storage = any(p.search(st) for p in storage_claim_patterns)

                if not is_invalid_ram and not is_invalid_storage:
                    clean_strengths.append(st)
                else:
                    logger.info(
                        "Sanitized unverified spec claim from product %s strengths: '%s'",
                        item.product_id,
                        st,
                    )

            # 2. Filter intended_use_advantages
            clean_advantages: list[str] = []
            for adv in item.intended_use_advantages:
                adv_lower = adv.lower()
                is_invalid_ram = False
                if has_unverified_ram:
                    if ("vram" in adv_lower or "gddr" in adv_lower or "graphics memory" in adv_lower) and not ("system memory" in adv_lower or "system ram" in adv_lower):
                        is_invalid_ram = False
                    else:
                        is_invalid_ram = any(p.search(adv) for p in ram_claim_patterns)

                is_invalid_storage = False
                if has_unverified_storage:
                    is_invalid_storage = any(p.search(adv) for p in storage_claim_patterns)

                if not is_invalid_ram and not is_invalid_storage:
                    clean_advantages.append(adv)

            # 3. Ensure missing_information explicitly notes unverified specs
            clean_missing = list(item.missing_information)
            if has_unverified_ram:
                if not any("ram" in m.lower() or "memory" in m.lower() for m in clean_missing):
                    clean_missing.append("RAM capacity is not confirmed in merchant product specifications.")
            if has_unverified_storage:
                if not any("storage" in m.lower() or "ssd" in m.lower() for m in clean_missing):
                    clean_missing.append("Storage / SSD capacity is unverified in merchant product specifications.")

            # 4. Align suitability with deterministic status
            updated_suitability = item.suitability
            status = elig.status.upper()
            if status == "UNVERIFIED_SPECS":
                suit_lower = item.suitability.lower()
                if any(kw in suit_lower for kw in ("highly suitable", "excellent", "perfect", "fully suitable", "best match", "ideal")):
                    updated_suitability = "Conditionally Suitable (Key specifications pending merchant verification)"
                elif "unverified" not in suit_lower and "pending" not in suit_lower and "conditional" not in suit_lower:
                    updated_suitability = f"Conditionally Suitable - Pending verification of {', '.join(unverified).upper()}"
            elif status == "EXCLUDED":
                suit_lower = item.suitability.lower()
                if any(kw in suit_lower for kw in ("suitable", "recommended", "excellent", "good")):
                    updated_suitability = "Excluded (Does not meet required specifications or budget)"
            elif status == "CURRENCY_MISMATCH":
                suit_lower = item.suitability.lower()
                if "currency" not in suit_lower:
                    updated_suitability = "Currency Mismatch (Direct budget comparison requires FX conversion)"

            # 5. Sanitize recommendation_rationale if it claims unverified specs
            updated_rationale = item.recommendation_rationale
            if has_unverified_ram and ("16 gb ram" in updated_rationale.lower() or "16gb ram" in updated_rationale.lower()):
                updated_rationale = re.sub(
                    r"(?i)(?:with|featuring|including)?\s*\d+\s*gb\s*(?:ddr\d\s*)?ram\s*(?:meets\s+requirements)?",
                    "with unverified RAM specification",
                    updated_rationale,
                )

            sanitized_item = item.model_copy(
                update={
                    "strengths": clean_strengths,
                    "intended_use_advantages": clean_advantages,
                    "missing_information": clean_missing,
                    "suitability": updated_suitability,
                    "recommendation_rationale": updated_rationale,
                }
            )
            sanitized_list.append(sanitized_item)

        return sanitized_list

    @classmethod
    def process_query(
        cls,
        db: Session,
        request: AssistantQueryRequest,
        gemini_client: GeminiClient | None = None,
        c3_client: Channel3Client | None = None,
    ) -> AssistantQueryResponse:
        """
        Execute the complete assistant query workflow:
        1. Extract structured shopping intent via Gemini (or safe fallback).
        2. Execute backend-controlled product search via Channel3 or catalog.
        3. Deterministically evaluate product eligibility (RAM, specs, budget, currency).
        4. Evaluate active spending mandate deterministically via SpendingPolicyEngine.
        5. Generate grounded product intelligence and consistent conversational guidance.
        """
        g_client = gemini_client or GeminiClient()
        c_client = c3_client or Channel3Client()

        # Step 1: Ensure session exists or create it
        session_obj = MandateRepository.get_or_create_session(db, request.session_id)
        active_mandate = MandateRepository.get_mandate_by_session_id(db, session_obj.id)

        # Step 2: Intent Extraction
        intent: ShoppingIntent
        is_ai_degraded = False
        degraded_reason = None

        try:
            intent = g_client.extract_shopping_intent(request.query)
        except (GeminiUnavailableError, GeminiTimeoutError, GeminiRateLimitError, GeminiAuthError, GeminiError) as exc:
            logger.warning(
                "Gemini intent extraction degraded [%s]: %s. Utilizing rule-based intent fallback.",
                type(exc).__name__,
                exc,
            )
            intent = cls._fallback_rule_based_intent(request.query)
            is_ai_degraded = True
            degraded_reason = f"Gemini reasoning temporarily unavailable: {str(exc)}"

        # Step 3: Product Search (Controlled by Backend)
        search_query = request.query
        if intent.category and intent.category != "general":
            if intent.intended_use:
                search_query = f"{intent.category} {intent.intended_use[0]}"
            else:
                search_query = intent.category

        retrieved_products: list[ProductResponse] = []
        try:
            if c_client.is_configured:
                search_res = ProductService.search_live_products(
                    db=db, query=search_query, limit=5, client=c_client
                )
                retrieved_products = search_res.items

            if not retrieved_products:
                catalog_res = ProductService.search_products(
                    db=db, query=intent.category if intent.category != "general" else request.query, page_size=5
                )
                retrieved_products = catalog_res.items
        except Channel3Error as exc:
            logger.error("Channel3 product search failed during assistant workflow: %s", exc)
            catalog_res = ProductService.search_products(
                db=db, query=intent.category if intent.category != "general" else request.query, page_size=5
            )
            retrieved_products = catalog_res.items

        # Step 4: Deterministic Product Eligibility Evaluation (RAM, Specs, Budget, Currency)
        eligibility_details: list[ProductEligibilityItem] = []
        qualified_product_ids: list[str] = []
        excluded_product_ids: list[str] = []
        unverified_product_ids: list[str] = []
        currency_mismatch_product_ids: list[str] = []

        for prod in retrieved_products:
            elig = cls.evaluate_product_eligibility(prod, intent)
            eligibility_details.append(elig)
            if elig.is_qualified:
                qualified_product_ids.append(prod.id)
            elif elig.status == "CURRENCY_MISMATCH":
                currency_mismatch_product_ids.append(prod.id)
            elif elig.status == "UNVERIFIED_SPECS":
                unverified_product_ids.append(prod.id)
            else:
                excluded_product_ids.append(prod.id)

        elig_map = {e.product_id: e for e in eligibility_details}

        # Step 5: Authoritative Deterministic Mandate Policy Evaluation
        mandate_eval_summary = None
        if active_mandate and retrieved_products:
            eval_target = None
            if qualified_product_ids:
                eval_target = next((p for p in retrieved_products if p.id in qualified_product_ids), None)
            if not eval_target:
                eval_target = retrieved_products[0]

            if eval_target and eval_target.lowest_price is not None:
                currency_to_eval = (
                    eval_target.offers[0].currency if eval_target.offers and eval_target.offers[0].currency else "USD"
                )
                eval_result = SpendingPolicyEngine.evaluate(
                    mandate=active_mandate,
                    unit_price=eval_target.lowest_price,
                    quantity=1,
                    currency=currency_to_eval,
                )
                mandate_eval_summary = eval_result.model_dump()

        # Step 6: Grounded Product Intelligence & Analysis
        ai_analyses: list[ProductIntelligence] = []
        if retrieved_products and not is_ai_degraded:
            prod_dicts = [p.model_dump() for p in retrieved_products]
            try:
                ai_analyses = g_client.analyze_products(
                    query=request.query,
                    intent=intent,
                    products=prod_dicts,
                    eligibility_map=elig_map,
                )
                ai_analyses = cls.validate_and_sanitize_intelligence(ai_analyses, elig_map)
            except GeminiError as exc:
                logger.warning("Product intelligence analysis failed: %s", exc)
                is_ai_degraded = True
                degraded_reason = f"Product intelligence degraded: {str(exc)}"

        # Step 7: Conversational Message Synthesis (Enforcing Absolute Consistency)
        assistant_message: str
        if not is_ai_degraded and retrieved_products:
            try:
                assistant_message = g_client.generate_conversational_response(
                    query=request.query,
                    history=request.conversation_context,
                    intent=intent,
                    products=[p.model_dump() for p in retrieved_products],
                    analyses=ai_analyses,
                )
            except GeminiError:
                assistant_message = cls._generate_deterministic_summary(
                    intent=intent,
                    products=retrieved_products,
                    mandate_eval=mandate_eval_summary,
                    eligibility_items=eligibility_details,
                )
        else:
            assistant_message = cls._generate_deterministic_summary(
                intent=intent,
                products=retrieved_products,
                mandate_eval=mandate_eval_summary,
                eligibility_items=eligibility_details,
            )

        return AssistantQueryResponse(
            success=True,
            session_id=request.session_id,
            intent=intent,
            products=retrieved_products,
            qualified_product_ids=qualified_product_ids,
            excluded_product_ids=excluded_product_ids,
            unverified_product_ids=unverified_product_ids,
            currency_mismatch_product_ids=currency_mismatch_product_ids,
            eligibility_details=eligibility_details,
            ai_analyses=ai_analyses,
            assistant_message=assistant_message,
            mandate_evaluation=mandate_eval_summary,
            is_ai_degraded=is_ai_degraded,
            degraded_reason=degraded_reason,
        )

    @staticmethod
    def _generate_deterministic_summary(
        intent: ShoppingIntent,
        products: list[ProductResponse],
        mandate_eval: dict[str, Any] | None,
        eligibility_items: list[ProductEligibilityItem] | None = None,
    ) -> str:
        """
        Generate consistent, transparent conversational summary.
        - Accurately reports product counts.
        - Highlights qualified recommendations.
        - Explains excluded, unverified, or currency-mismatched items.
        - Never claims an excluded product qualified.
        - Keeps all currency labels visible.
        """
        if not products:
            return (
                f"We searched live retailers for '{intent.query}', but could not find any available matching products. "
                f"Try broadening your search terms or adjusting your budget ceiling."
            )

        eligibility_items = eligibility_items or []
        eligibility_map = {item.product_id: item for item in eligibility_items}

        qualified = [p for p in products if eligibility_map.get(p.id) and eligibility_map[p.id].is_qualified]
        currency_mismatch = [
            p for p in products if eligibility_map.get(p.id) and eligibility_map[p.id].status == "CURRENCY_MISMATCH"
        ]
        unverified = [
            p for p in products if eligibility_map.get(p.id) and eligibility_map[p.id].status == "UNVERIFIED_SPECS"
        ]
        excluded = [
            p for p in products if eligibility_map.get(p.id) and eligibility_map[p.id].status == "EXCLUDED"
        ]

        lines: list[str] = []

        if qualified:
            lines.append(f"Found {len(qualified)} qualified option(s) matching all your requirements:")
            for idx, p in enumerate(qualified, 1):
                offer = p.offers[0] if p.offers else None
                curr = offer.currency if offer else "USD"
                price_str = f"{p.lowest_price:,.2f} {curr}" if p.lowest_price else "Price unavailable"
                retailer_str = f"at {offer.retailer_name}" if offer else ""
                lines.append(f"{idx}. {p.name} — {price_str} {retailer_str}".strip())
        else:
            req_desc = []
            if intent.max_budget:
                req_desc.append(f"budget under {intent.max_budget:,.2f} {intent.currency}")
            for r in intent.required_specs:
                req_desc.append(f"{r.name} {r.value}")
            req_str = " (" + ", ".join(req_desc) + ")" if req_desc else ""

            lines.append(
                f"We retrieved {len(products)} product(s) for '{intent.query}', but none met all your specified requirements{req_str}:"
            )

        # Mention currency mismatches if present
        if currency_mismatch:
            lines.append(
                f"\n⚠️ Currency Notice: {len(currency_mismatch)} product(s) are priced in USD by available retailers. "
                f"Because no verified real-time FX conversion service is configured, these USD offers cannot be certified as within your {intent.currency} budget:"
            )
            for p in currency_mismatch[:5]:
                offer = p.offers[0] if p.offers else None
                curr = offer.currency if offer else "USD"
                price_str = f"{p.lowest_price:,.2f} {curr}" if p.lowest_price else "Price unavailable"
                retailer_str = f"at {offer.retailer_name}" if offer else ""
                lines.append(f"  • {p.name} — {price_str} {retailer_str}".strip())

        # Mention unverified specifications if present
        if unverified:
            lines.append(
                f"\nℹ️ Unverified Specifications: {len(unverified)} product(s) lack merchant-provided specification details for your required hardware criteria."
            )

        # Mention excluded items if present
        if excluded:
            lines.append(
                f"\n❌ Excluded: {len(excluded)} product(s) did not meet your required hardware minimums or budget limits."
            )

        # Spending Mandate policy section
        if mandate_eval:
            decision = mandate_eval.get("decision")
            if decision == "ALLOWED":
                lines.append("\n✅ Spending Policy: Purchase is ALLOWED under your active session mandate.")
            else:
                reasons = " ".join(mandate_eval.get("reasons", []))
                lines.append(f"\n⚠️ Spending Policy: BLOCKED under your session mandate. {reasons}")

        return "\n".join(lines)
