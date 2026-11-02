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
        """Extract RAM in GB from product specifications, title, or description."""
        specs = product.specifications or {}
        for key in ("ram", "RAM", "memory", "Memory", "system_memory", "System Memory (RAM)", "ram_memory"):
            if key in specs and specs[key]:
                val_str = str(specs[key]).lower()
                m = re.search(r"(\d+)\s*(?:gb|gigabytes?)", val_str)
                if m:
                    return float(m.group(1)), f"specs.{key}: {specs[key]}"

        for text, src in [(product.name, "product title"), (product.description, "description")]:
            if text:
                m = re.search(r"(\d+)\s*(?:gb|gigabytes?)\s*(?:ram|memory)", text.lower())
                if m:
                    return float(m.group(1)), f"{src}: {m.group(0)}"

        return None, "Not specified"

    @staticmethod
    def _extract_storage_from_product(product: ProductResponse) -> tuple[float | None, str]:
        """Extract storage in GB from product specifications, title, or description."""
        specs = product.specifications or {}
        for key in ("storage", "Storage", "ssd", "SSD", "hard_drive", "drive", "capacity"):
            if key in specs and specs[key]:
                val_str = str(specs[key]).lower()
                tb_m = re.search(r"(\d+)\s*(?:tb|terabytes?)", val_str)
                if tb_m:
                    return float(tb_m.group(1)) * 1024.0, f"specs.{key}: {specs[key]}"
                gb_m = re.search(r"(\d+)\s*(?:gb|gigabytes?)", val_str)
                if gb_m:
                    return float(gb_m.group(1)), f"specs.{key}: {specs[key]}"

        for text, src in [(product.name, "product title"), (product.description, "description")]:
            if text:
                tb_m = re.search(r"(\d+)\s*tb\s*(?:ssd|storage|nvme)", text.lower())
                if tb_m:
                    return float(tb_m.group(1)) * 1024.0, f"{src}: {tb_m.group(0)}"
                gb_m = re.search(r"(\d+)\s*gb\s*(?:ssd|storage|nvme)", text.lower())
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
                )
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
