"""
AI-Powered Multilingual Shopping Intelligence Platform
Checkout Service & Business Logic Orchestrator.
Coordinates product validation, deterministic spending policy gates,
idempotent PayPal Sandbox order creation, buyer approval, and authoritative capture verification.
Enforces strict boundaries: AI suggests, Backend validates, User approves, PayPal processes.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
import logging
from typing import Any
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.shopping import Product, RetailerOffer, ShoppingSession, SpendingMandate
from backend.app.models.payment import (
    PaymentOrder,
    OrderItem,
    PaymentCapture,
    PaymentOrderStatus,
    InvalidStateTransitionError,
    PaymentVerificationError,
    CaptureAmountMismatchError,
    CaptureCurrencyMismatchError,
    UnverifiedCaptureError,
    generate_uuid,
)
from backend.app.repositories.mandate_repository import MandateRepository
from backend.app.schemas.checkout import (
    CheckoutOrderCreate,
    PaymentOrderResponse,
    OrderItemResponse,
    PaymentCaptureResponse,
    PaymentHistoryItemResponse,
    PaymentOrderListResponse,
    RetailerRedirectResponse,
)
from backend.app.services.paypal_client import (
    PayPalClient,
    PayPalError,
    PayPalAuthError,
    PayPalRateLimitError,
    PayPalTimeoutError,
    PayPalOrderNotFoundError,
    PayPalCaptureError,
    PayPalAPIError,
)
from backend.app.services.policy_engine import SpendingPolicyEngine

logger = logging.getLogger(__name__)

# Authoritative list of standard currencies supported in PayPal Sandbox
SUPPORTED_PAYPAL_CURRENCIES = {
    "USD", "EUR", "GBP", "CAD", "AUD", "JPY", "INR", "CHF", "HKD", "SGD", "SEK", "NZD", "MXN"
}


# -------------------------------------------------------------------------
# Checkout Exceptions Hierarchy
# -------------------------------------------------------------------------

class CheckoutError(Exception):
    """Base exception for checkout service errors."""
    pass


class InvalidSessionError(CheckoutError):
    """Raised when an active session cannot be resolved."""
    pass


class ProductNotFoundError(CheckoutError):
    """Raised when a requested product ID is not found."""
    pass


class RetailerOfferNotFoundError(CheckoutError):
    """Raised when a requested retailer offer ID is not found."""
    pass


class OfferOutOfStockError(CheckoutError):
    """Raised when a selected offer is out of stock."""
    pass


class ExternalRetailerCheckoutError(CheckoutError):
    """
    Raised when a user attempts internal demo checkout for a live Channel3 marketplace offer.
    Directs the user to complete purchase on the external merchant's website.
    """

    def __init__(
        self,
        retailer_name: str,
        product_url: str,
        product_name: str,
        price: Decimal,
        currency: str,
    ):
        super().__init__(
            f"Item '{product_name}' is sold by external merchant '{retailer_name}'. "
            f"You will complete your purchase directly on their website."
        )
        self.retailer_name = retailer_name
        self.product_url = product_url
        self.product_name = product_name
        self.price = price
        self.currency = currency


class MandatePolicyViolationError(CheckoutError):
    """Raised when a purchase violates deterministic spending limits."""

    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class UnsupportedCurrencyError(CheckoutError):
    """Raised when an order currency is not supported by PayPal Sandbox."""
    pass


class OrderExpiredError(CheckoutError):
    """Raised when attempting capture on an order whose 15-minute TTL elapsed."""
    pass


class OrderOwnershipError(CheckoutError):
    """Raised when attempting to access or capture an order belonging to another session."""
    pass


class InvalidOrderStateError(CheckoutError):
    """Raised when an order is not in a valid state for the requested operation."""
    pass


class DuplicateCaptureError(CheckoutError):
    """Raised when a capture settlement has already been recorded."""
    pass


class CaptureReconciliationRequiredError(CheckoutError):
    """Raised when a capture request outcome is uncertain and requires reconciliation."""
    pass


# -------------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------------

def mask_email(email: str | None) -> str | None:
    """Mask email address for privacy (e.g. buyer@example.com -> b***r@example.com)."""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + "***" + local[-1]
    return f"{masked_local}@{domain}"


# -------------------------------------------------------------------------
# Checkout Service
# -------------------------------------------------------------------------

class CheckoutService:
    """
    Coordinates checkout initialization, policy validation, order creation,
    and authoritative payment capture verification.
    """

    @staticmethod
    def create_checkout_order(
        db: Session,
        request: CheckoutOrderCreate,
        paypal_client: PayPalClient | None = None,
    ) -> PaymentOrderResponse:
        """
        Create a new payment order and generate a PayPal Sandbox approval link.
        Validates product eligibility, offer freshness, and spending mandate limits.
        """
        client = paypal_client or PayPalClient()

        # 1. Resolve or verify active guest session
        session = None
        if request.session_id:
            session = db.get(ShoppingSession, request.session_id)
            if not session and not request.session_identifier:
                raise InvalidSessionError(f"Session '{request.session_id}' not found.")

        if not session and request.session_identifier:
            session = MandateRepository.get_or_create_session(
                db=db,
                session_identifier=request.session_identifier,
            )

        if not session:
            raise InvalidSessionError("Could not resolve an active guest shopping session.")

        # 2. Local session-scoped idempotency check
        if request.idempotency_key:
            existing_order = (
                db.query(PaymentOrder)
                .filter_by(session_id=session.id, idempotency_key=request.idempotency_key)
                .first()
            )
            if existing_order:
                # If already completed or still valid and active, return existing order
                if existing_order.status == PaymentOrderStatus.COMPLETED.value:
                    logger.info("Idempotent hit: returning existing COMPLETED order %s", existing_order.id)
                    return PaymentOrderResponse.model_validate(existing_order)
                if not existing_order.is_expired and existing_order.status in (
                    PaymentOrderStatus.CREATED.value,
                    PaymentOrderStatus.APPROVED.value,
                ):
                    logger.info("Idempotent hit: returning existing active order %s", existing_order.id)
                    return PaymentOrderResponse.model_validate(existing_order)

        # 3. Validate items, pricing, and purchase track
        order_currency = request.currency.strip().upper()
        if order_currency not in SUPPORTED_PAYPAL_CURRENCIES:
            raise UnsupportedCurrencyError(
                f"Currency '{order_currency}' is not supported for PayPal Sandbox checkout."
            )

        validated_items: list[dict[str, Any]] = []
        max_item_unit_price = Decimal("0.00")
        total_quantity = 0

        for item_in in request.items:
            prod_id = item_in.product_id
            offer_id = item_in.retailer_offer_id

            if offer_id:
                offer = db.query(RetailerOffer).filter_by(id=offer_id).first()
                if not offer:
                    raise RetailerOfferNotFoundError(f"Retailer offer '{offer_id}' was not found.")

                product = offer.product
                if not product:
                    raise ProductNotFoundError(f"Product for offer '{offer_id}' was not found.")

                # PURCHASE TRACK ENFORCEMENT:
                # Reject external Channel3 marketplace items from internal demo checkout!
                if not product.is_synthetic or product.provider != "synthetic":
                    logger.info("External marketplace item requested: redirecting to %s", offer.product_url)
                    raise ExternalRetailerCheckoutError(
                        retailer_name=offer.retailer_name,
                        product_url=offer.product_url,
                        product_name=product.name,
                        price=Decimal(str(offer.price)),
                        currency=offer.currency,
                    )

                # Revalidate stock availability
                if offer.availability.upper() not in ("IN_STOCK", "LIMITED_STOCK", "LOW_STOCK"):
                    raise OfferOutOfStockError(
                        f"Offer from '{offer.retailer_name}' is currently {offer.availability}."
                    )

                # Server-calculated authoritative price
                server_unit_price = Decimal(str(offer.price))
                item_currency = offer.currency.strip().upper()
                product_name = product.name
                retailer_name = offer.retailer_name
            elif prod_id:
                product = db.query(Product).filter_by(id=prod_id).first()
                if not product:
                    raise ProductNotFoundError(f"Product '{prod_id}' was not found.")

                if not product.is_synthetic or product.provider != "synthetic":
                    raise ExternalRetailerCheckoutError(
                        retailer_name=product.brand,
                        product_url=product.image_url or "https://example.com",
                        product_name=product.name,
                        price=Decimal(str(item_in.unit_price)),
                        currency=order_currency,
                    )

                server_unit_price = Decimal(str(item_in.unit_price))
                item_currency = item_in.currency.strip().upper()
                product_name = product.name
                retailer_name = item_in.retailer_name or "Synthetic Demo Store"
            else:
                # Custom synthetic item snapshot
                server_unit_price = Decimal(str(item_in.unit_price))
                item_currency = item_in.currency.strip().upper()
                product_name = item_in.product_name
                retailer_name = item_in.retailer_name or "Demo Store"

            # Enforce currency consistency across items
            if item_currency != order_currency:
                raise UnsupportedCurrencyError(
                    f"Item currency '{item_currency}' differs from order currency '{order_currency}'."
                )

            quantity = max(1, item_in.quantity)
            subtotal = server_unit_price * quantity
            total_quantity += quantity
            if server_unit_price > max_item_unit_price:
                max_item_unit_price = server_unit_price

            validated_items.append({
                "product_id": prod_id,
                "retailer_offer_id": offer_id,
                "product_name": product_name,
                "retailer_name": retailer_name,
                "quantity": quantity,
                "unit_price": server_unit_price,
                "subtotal": subtotal,
                "currency": order_currency,
            })

        total_amount = sum((it["subtotal"] for it in validated_items), Decimal("0.00"))

        # 4. Authoritative deterministic spending mandate revalidation
        mandate = None
        if request.mandate_id:
            mandate = db.query(SpendingMandate).filter_by(id=request.mandate_id).first()
        if not mandate:
            mandate = MandateRepository.get_mandate_by_session_id(db, session.id)

        if mandate:
            evaluation = SpendingPolicyEngine.evaluate(
                mandate=mandate,
                unit_price=float(max_item_unit_price),
                quantity=total_quantity,
                currency=order_currency,
            )
            if not evaluation.is_allowed:
                logger.warning("Checkout blocked by spending policy: %s", evaluation.reasons)
                raise MandatePolicyViolationError(reasons=evaluation.reasons)

        # 5. Database Transaction 1: Persist Local PaymentOrder Draft
        paypal_req_id = generate_uuid()
        client_idemp_key = request.idempotency_key or generate_uuid()
        order_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

        order = PaymentOrder(
            session_id=session.id,
            mandate_id=mandate.id if mandate else None,
            paypal_request_id=paypal_req_id,
            idempotency_key=client_idemp_key,
            status=PaymentOrderStatus.CREATED.value,
            total_amount=total_amount,
            currency=order_currency,
            payment_provider="paypal_sandbox",
            order_type="SANDBOX_DEMO",
            expires_at=order_expires_at,
        )
        db.add(order)
        db.flush()

        for it in validated_items:
            db_item = OrderItem(
                payment_order_id=order.id,
                product_id=it["product_id"],
                retailer_offer_id=it["retailer_offer_id"],
                product_name=it["product_name"],
                retailer_name=it["retailer_name"],
                quantity=it["quantity"],
                unit_price=it["unit_price"],
                subtotal=it["subtotal"],
                currency=it["currency"],
            )
            db.add(db_item)

        db.commit()
        db.refresh(order)
        logger.info("Persisted local PaymentOrder draft: %s [Ref: %s]", order.id, order.internal_order_number)

        # 6. Outside DB Transaction: External PayPal Orders v2 Call
        try:
            pp_order_data = client.create_order(
                total_amount=total_amount,
                currency=order_currency,
                internal_order_number=order.internal_order_number,
                paypal_request_id=paypal_req_id,
                description=f"Order {order.internal_order_number} Demo Checkout",
            )
            paypal_order_id = pp_order_data["id"]
            approval_url = pp_order_data.get("_extracted_approval_url")
        except Exception as exc:
            logger.error("PayPal order creation failed for local order %s: %s", order.id, exc)
            order.status = PaymentOrderStatus.FAILED.value
            db.commit()
            raise

        # 7. Database Transaction 2: Update Order with PayPal Order ID
        order.paypal_order_id = paypal_order_id
        db.commit()
        db.refresh(order)

        response = PaymentOrderResponse.model_validate(order)
        response.approval_url = approval_url
        return response

    @staticmethod
    def capture_checkout_order(
        db: Session,
        order_id: str,
        session_id: str,
        paypal_client: PayPalClient | None = None,
    ) -> PaymentOrderResponse:
        """
        Capture an approved PayPal order and verify settlement proof.
        Atomically establishes CAPTURE_PENDING, executes capture with stable PayPal-Request-Id,
        validates amounts, currencies, and records verified settlement.
        """
        client = paypal_client or PayPalClient()

        # 1. Fetch local order
        order = db.query(PaymentOrder).filter_by(id=order_id).first()
        if not order:
            raise InvalidOrderStateError(f"Payment order '{order_id}' was not found.")

        # 2. Verify session ownership
        if order.session_id and order.session_id != session_id:
            raise OrderOwnershipError("Order does not belong to the active shopping session.")

        # 3. Idempotent check: if already completed, return existing verified order
        if order.status == PaymentOrderStatus.COMPLETED.value:
            logger.info("Idempotent capture hit: order %s is already COMPLETED", order_id)
            return PaymentOrderResponse.model_validate(order)

        # 4. Verify order state is capturable
        if order.status in (PaymentOrderStatus.CANCELLED.value, PaymentOrderStatus.EXPIRED.value, PaymentOrderStatus.FAILED.value):
            raise InvalidOrderStateError(f"Cannot capture order in terminal '{order.status}' state.")

        if order.is_expired:
            logger.warning("Order %s expired prior to capture", order_id)
            order.status = PaymentOrderStatus.EXPIRED.value
            db.commit()
            raise OrderExpiredError(f"Order '{order.internal_order_number}' expired (15-minute validity window elapsed).")

        # 5. Database Transaction 1: Atomically lock order in CAPTURE_PENDING
        # Allocate stable capture request ID if not yet assigned
        if not order.paypal_capture_request_id:
            order.paypal_capture_request_id = generate_uuid()

        if order.status == PaymentOrderStatus.CREATED.value:
            order.transition_to(PaymentOrderStatus.APPROVED)
        order.transition_to(PaymentOrderStatus.CAPTURE_PENDING)
        db.commit()
        db.refresh(order)
        logger.info("Order %s locked in CAPTURE_PENDING [CaptureReqId: %s]", order.id, order.paypal_capture_request_id)

        # 6. Outside DB Transaction: Call PayPal Capture Endpoint
        capture_data = None
        try:
            capture_data = client.capture_order(
                paypal_order_id=order.paypal_order_id,  # type: ignore[arg-type]
                paypal_capture_request_id=order.paypal_capture_request_id,
            )
        except PayPalTimeoutError as exc:
            logger.warning("Capture call timed out for order %s. Initiating reconciliation check...", order.id)
            # Reconcile status before failing
            try:
                order_details = client.get_order_details(order.paypal_order_id)  # type: ignore[arg-type]
                if order_details.get("status") == "COMPLETED":
                    logger.info("Reconciliation confirmed order %s completed on PayPal", order.id)
                    capture_data = order_details
                else:
                    raise CaptureReconciliationRequiredError(
                        "Capture request timed out. Gateway state is uncertain; manual reconciliation in progress."
                    ) from exc
            except Exception:
                raise CaptureReconciliationRequiredError(
                    "Capture request timed out. Gateway state is uncertain; manual reconciliation in progress."
                ) from exc

        # 7. Extract authoritative capture evidence
        captures_list = []
        purchase_units = capture_data.get("purchase_units", [])
        for pu in purchase_units:
            payments = pu.get("payments", {})
            captures_list.extend(payments.get("captures", []))

        if not captures_list:
            logger.error("PayPal capture response missing payments.captures array: %s", capture_data)
            raise PayPalCaptureError("PayPal capture response did not contain capture settlement details.")

        primary_capture = captures_list[0]
        paypal_capture_id = primary_capture.get("id")
        capture_status = primary_capture.get("status", "COMPLETED")
        captured_amount_str = primary_capture.get("amount", {}).get("value", "0.00")
        captured_currency = primary_capture.get("amount", {}).get("currency_code", "USD")
        captured_amount = Decimal(captured_amount_str)

        if not paypal_capture_id:
            raise PayPalCaptureError("PayPal capture record missing capture ID.")

        # Check duplicate capture ID
        existing_cap = db.query(PaymentCapture).filter_by(paypal_capture_id=paypal_capture_id).first()
        if existing_cap:
            raise DuplicateCaptureError(f"PayPal capture ID '{paypal_capture_id}' is already recorded.")

        # Extract buyer info (safely masked)
        payer = capture_data.get("payer", {})
        payer_id = payer.get("payer_id") or capture_data.get("payment_source", {}).get("paypal", {}).get("account_id")
        raw_email = payer.get("email_address") or capture_data.get("payment_source", {}).get("paypal", {}).get("email_address")
        masked_email_val = mask_email(raw_email)

        # 8. Database Transaction 2: Persist Verified Capture and Complete Order
        capture_record = PaymentCapture(
            payment_order_id=order.id,
            paypal_order_id=order.paypal_order_id,
            paypal_capture_id=paypal_capture_id,
            captured_amount=captured_amount,
            currency=captured_currency,
            capture_status=capture_status,
            is_verified=True,  # Established strictly by backend REST response
            paypal_payer_id=payer_id,
            paypal_payer_email_masked=masked_email_val,
            raw_response_summary={
                "id": paypal_capture_id,
                "status": capture_status,
                "create_time": primary_capture.get("create_time"),
            },
        )
        db.add(capture_record)

        # Non-bypassable verification boundary validates amounts, currencies, and status
        order.complete_with_verified_capture(capture_record)
        db.commit()
        db.refresh(order)
        logger.info("Order %s successfully COMPLETED with verified capture %s", order.id, paypal_capture_id)

        return PaymentOrderResponse.model_validate(order)

    @staticmethod
    def get_order_status(db: Session, order_id: str, session_id: str) -> PaymentOrderResponse:
        """Retrieve authoritative status and item snapshots for a payment order."""
        order = db.query(PaymentOrder).filter_by(id=order_id).first()
        if not order:
            raise InvalidOrderStateError(f"Payment order '{order_id}' was not found.")
        if order.session_id and order.session_id != session_id:
            raise OrderOwnershipError("Order does not belong to the active shopping session.")
        return PaymentOrderResponse.model_validate(order)

    @staticmethod
    def get_session_payment_history(
        db: Session,
        session_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> PaymentOrderListResponse:
        """Retrieve paginated payment history for a guest shopping session."""
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        offset = (page - 1) * page_size

        total = db.query(func.count(PaymentOrder.id)).filter_by(session_id=session_id).scalar() or 0
        orders = (
            db.query(PaymentOrder)
            .filter_by(session_id=session_id)
            .order_by(PaymentOrder.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

        history_items = []
        for ord_item in orders:
            primary_cap_id = ord_item.captures[0].paypal_capture_id if ord_item.captures else None
            captured_at = ord_item.captures[0].captured_at if ord_item.captures else None
            history_items.append(
                PaymentHistoryItemResponse(
                    id=ord_item.id,
                    internal_order_number=ord_item.internal_order_number,
                    status=ord_item.status,
                    total_amount=ord_item.total_amount,
                    currency=ord_item.currency,
                    item_count=len(ord_item.items),
                    paypal_order_id=ord_item.paypal_order_id,
                    paypal_capture_id=primary_cap_id,
                    created_at=ord_item.created_at,
                    captured_at=captured_at,
                )
            )

        return PaymentOrderListResponse(
            orders=history_items,
            total=total,
            session_id=session_id,
        )
