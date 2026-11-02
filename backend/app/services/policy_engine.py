"""
AI-Powered Multilingual Shopping Intelligence Platform
Deterministic Spending Policy Engine.
Completely independent of AI / LLMs — enforces hard budgetary and safety constraints.
"""

from backend.app.models.shopping import SpendingMandate
from backend.app.schemas.mandate import PurchaseEvaluationResponse


class SpendingPolicyEngine:
    """
    Deterministic rule evaluation engine for spending mandates.
    CRITICAL SECURITY INVARIANT:
    AI models (e.g. Gemini) may suggest, translate, or explain, but this deterministic
    engine ALWAYS holds ultimate authority over purchase authorization.
    """

    @staticmethod
    def evaluate(
        mandate: SpendingMandate | None,
        unit_price: float,
        quantity: int,
        currency: str = "USD",
    ) -> PurchaseEvaluationResponse:
        """
        Evaluate a candidate purchase against the session's active spending mandate.
        Returns an authoritative ALLOWED or BLOCKED decision with human-readable reasons.
        """
        total_cost = round(unit_price * quantity, 2)
        norm_currency = currency.strip().upper()

        # Rule 0: Mandate must exist
        if mandate is None:
            return PurchaseEvaluationResponse(
                decision="BLOCKED",
                is_allowed=False,
                reasons=[
                    "No active spending mandate found for this session. "
                    "You must configure a spending mandate before initiating a purchase."
                ],
                purchase_amount=total_cost,
                quantity=quantity,
                currency=norm_currency,
                mandate_budget=None,
                mandate_max_item_price=None,
                mandate_max_quantity=None,
                remaining_budget_after_purchase=None,
            )

        reasons: list[str] = []

        # Rule 1: Currency consistency
        if mandate.currency.upper() != norm_currency:
            reasons.append(
                f"Purchase currency ({norm_currency}) does not match your active mandate currency "
                f"({mandate.currency.upper()}). Cross-currency conversion is not permitted under this mandate."
            )

        # Rule 2: Single item price ceiling
        if unit_price > mandate.maximum_item_price:
            reasons.append(
                f"Item unit price of ${unit_price:,.2f} exceeds your maximum permitted item price limit "
                f"of ${mandate.maximum_item_price:,.2f}."
            )

        # Rule 3: Quantity ceiling
        if quantity > mandate.maximum_quantity:
            reasons.append(
                f"Requested quantity of {quantity} item(s) exceeds your maximum permitted quantity limit "
                f"of {mandate.maximum_quantity} item(s)."
            )

        # Rule 4: Total budget ceiling
        if total_cost > mandate.total_budget:
            reasons.append(
                f"Total purchase cost of ${total_cost:,.2f} exceeds your remaining mandate budget "
                f"of ${mandate.total_budget:,.2f}."
            )

        # Final Decision Resolution
        if reasons:
            return PurchaseEvaluationResponse(
                decision="BLOCKED",
                is_allowed=False,
                reasons=reasons,
                purchase_amount=total_cost,
                quantity=quantity,
                currency=norm_currency,
                mandate_budget=mandate.total_budget,
                mandate_max_item_price=mandate.maximum_item_price,
                mandate_max_quantity=mandate.maximum_quantity,
                remaining_budget_after_purchase=round(mandate.total_budget - total_cost, 2),
            )

        remaining_budget = round(mandate.total_budget - total_cost, 2)
        return PurchaseEvaluationResponse(
            decision="ALLOWED",
            is_allowed=True,
            reasons=["Purchase conforms to all spending mandate budget, item price, and quantity limits."],
            purchase_amount=total_cost,
            quantity=quantity,
            currency=norm_currency,
            mandate_budget=mandate.total_budget,
            mandate_max_item_price=mandate.maximum_item_price,
            mandate_max_quantity=mandate.maximum_quantity,
            remaining_budget_after_purchase=remaining_budget,
        )
