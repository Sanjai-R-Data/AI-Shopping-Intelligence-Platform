"""
AI-Powered Multilingual Shopping Intelligence Platform
Phase 4.1 & 4.1.1 Payment Models & Safety Hardening Test Suite.
Tests PaymentOrder, OrderItem, PaymentCapture models, state transitions,
decimal precision, foreign key constraints, session deletion preservation,
session-scoped idempotency, and trusted completion invariants.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
    generate_order_number,
    generate_uuid,
)
from backend.app.schemas.checkout import (
    OrderItemCreate,
    OrderItemResponse,
    PaymentCaptureResponse,
    CheckoutOrderCreate,
    PaymentOrderResponse,
    PaymentHistoryItemResponse,
    PaymentOrderListResponse,
)


# =============================================================================
# Category 1: PaymentOrder Creation, Attributes & Relationships
# =============================================================================

def test_payment_order_creation_defaults(test_session: Session):
    """Verify PaymentOrder can be created with defaults and queried successfully."""
    session = ShoppingSession(session_identifier="guest_sess_1001")
    test_session.add(session)
    test_session.commit()

    order = PaymentOrder(
        session_id=session.id,
        total_amount=Decimal("149.99"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order)
    test_session.commit()

    # Query back
    saved_order = test_session.query(PaymentOrder).filter_by(id=order.id).first()
    assert saved_order is not None
    assert saved_order.id == order.id
    assert saved_order.session_id == session.id
    assert saved_order.status == PaymentOrderStatus.CREATED.value
    assert saved_order.total_amount == Decimal("149.99")
    assert isinstance(saved_order.total_amount, Decimal)
    assert saved_order.currency == "USD"
    assert saved_order.payment_provider == "paypal_sandbox"
    assert saved_order.order_type == "SANDBOX_DEMO"
    assert saved_order.internal_order_number.startswith("ORD-")
    assert len(saved_order.paypal_request_id) > 10
    assert len(saved_order.idempotency_key) > 10
    assert saved_order.paypal_order_id is None
    assert saved_order.mandate_id is None
    assert saved_order.created_at is not None
    assert saved_order.updated_at is not None
    assert saved_order.is_expired is False


def test_payment_order_with_mandate_relationship(test_session: Session):
    """Verify PaymentOrder links to SpendingMandate and session backrefs work."""
    session = ShoppingSession(session_identifier="guest_sess_mandate_1")
    test_session.add(session)
    test_session.commit()

    mandate = SpendingMandate(
        session_id=session.id,
        total_budget=500.0,
        maximum_item_price=200.0,
        maximum_quantity=2,
        currency="USD",
    )
    test_session.add(mandate)
    test_session.commit()

    order = PaymentOrder(
        session_id=session.id,
        mandate_id=mandate.id,
        total_amount=Decimal("189.50"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order)
    test_session.commit()

    # Verify bidirectional navigation
    queried_order = test_session.query(PaymentOrder).filter_by(id=order.id).first()
    assert queried_order.mandate is not None
    assert queried_order.mandate.id == mandate.id
    assert queried_order.session.id == session.id
    assert order in session.orders
    assert order in mandate.orders


# =============================================================================
# Category 2: OrderItem Relationships, Cascade & Historical Snapshots
# =============================================================================

def test_order_items_creation_and_cascade_delete(test_session: Session):
    """Verify OrderItems capture product snapshots and cascade-delete when order is deleted."""
    session = ShoppingSession(session_identifier="guest_sess_items_1")
    test_session.add(session)
    test_session.commit()

    # Create catalog product and offer
    prod = Product(
        name="Dell XPS 15",
        brand="Dell",
        category="Electronics",
        description="Premium laptop",
        specifications={"ram": "32GB"},
    )
    test_session.add(prod)
    test_session.commit()

    offer = RetailerOffer(
        product_id=prod.id,
        retailer_name="Dell Store",
        price=1899.00,
        currency="USD",
        product_url="https://dell.com/xps15",
        availability="IN_STOCK",
    )
    test_session.add(offer)
    test_session.commit()

    order = PaymentOrder(
        session_id=session.id,
        total_amount=Decimal("1929.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order)
    test_session.commit()

    # Add items to order
    item1 = OrderItem(
        payment_order_id=order.id,
        product_id=prod.id,
        retailer_offer_id=offer.id,
        product_name="Dell XPS 15 (32GB RAM)",
        retailer_name="Dell Store",
        quantity=1,
        unit_price=Decimal("1899.00"),
        subtotal=Decimal("1899.00"),
        currency="USD",
    )
    item2 = OrderItem(
        payment_order_id=order.id,
        product_name="Laptop Sleeve Case",
        retailer_name="Generic",
        quantity=1,
        unit_price=Decimal("30.00"),
        subtotal=Decimal("30.00"),
        currency="USD",
    )
    test_session.add_all([item1, item2])
    test_session.commit()

    # Verify query
    queried_order = test_session.query(PaymentOrder).filter_by(id=order.id).first()
    assert len(queried_order.items) == 2
    item_names = [i.product_name for i in queried_order.items]
    assert "Dell XPS 15 (32GB RAM)" in item_names
    assert "Laptop Sleeve Case" in item_names

    # Delete order and verify order items are cascade deleted while Product/Offer remain intact
    test_session.delete(queried_order)
    test_session.commit()

    remaining_items = test_session.query(OrderItem).filter_by(payment_order_id=order.id).all()
    assert len(remaining_items) == 0

    # Ensure product and offer were NOT deleted
    assert test_session.query(Product).filter_by(id=prod.id).first() is not None
    assert test_session.query(RetailerOffer).filter_by(id=offer.id).first() is not None


# =============================================================================
# Category 3: PaymentCapture Persistence & Relationship
# =============================================================================

def test_payment_capture_persistence_and_relationships(test_session: Session):
    """Verify PaymentCapture records are linked to PaymentOrder and store settlement audit data."""
    session = ShoppingSession(session_identifier="guest_sess_capture_1")
    test_session.add(session)
    test_session.commit()

    order = PaymentOrder(
        session_id=session.id,
        paypal_order_id="5O190127TN364715T",
        total_amount=Decimal("249.99"),
        currency="USD",
        status=PaymentOrderStatus.CREATED.value,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order)
    test_session.commit()

    order.transition_to(PaymentOrderStatus.APPROVED)
    order.transition_to(PaymentOrderStatus.CAPTURE_PENDING)

    capture = PaymentCapture(
        payment_order_id=order.id,
        paypal_order_id="5O190127TN364715T",
        paypal_capture_id="CAP-9876543210ABC",
        captured_amount=Decimal("249.99"),
        currency="USD",
        capture_status="COMPLETED",
        is_verified=True,
        paypal_payer_id="PAYER-US-554433",
        paypal_payer_email_masked="s***r@example.com",
        raw_response_summary={"status": "COMPLETED", "amount": {"value": "249.99", "currency_code": "USD"}},
    )
    order.complete_with_verified_capture(capture)
    test_session.add(capture)
    test_session.commit()

    # Query back
    saved_capture = test_session.query(PaymentCapture).filter_by(paypal_capture_id="CAP-9876543210ABC").first()
    assert saved_capture is not None
    assert saved_capture.payment_order_id == order.id
    assert saved_capture.captured_amount == Decimal("249.99")
    assert isinstance(saved_capture.captured_amount, Decimal)
    assert saved_capture.is_verified is True
    assert saved_capture.paypal_payer_email_masked == "s***r@example.com"
    assert saved_capture.raw_response_summary["status"] == "COMPLETED"
    assert saved_capture.order.id == order.id
    assert order.captures[0].paypal_capture_id == "CAP-9876543210ABC"


# =============================================================================
# Category 4: Uniqueness Constraints (PayPal IDs, Capture IDs, Global Keys)
# =============================================================================

def test_unique_paypal_order_id_constraint(test_session: Session):
    """Enforce uniqueness constraint on paypal_order_id."""
    session = ShoppingSession(session_identifier="guest_sess_uniq_pp_order")
    test_session.add(session)
    test_session.commit()

    order1 = PaymentOrder(
        session_id=session.id,
        paypal_order_id="PAYPAL-ORDER-DUPLICATE-1",
        total_amount=Decimal("50.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order1)
    test_session.commit()

    order2 = PaymentOrder(
        session_id=session.id,
        paypal_order_id="PAYPAL-ORDER-DUPLICATE-1",  # Duplicate!
        total_amount=Decimal("75.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order2)
    with pytest.raises(IntegrityError):
        test_session.commit()
    test_session.rollback()


def test_unique_paypal_capture_id_constraint(test_session: Session):
    """Enforce uniqueness constraint on paypal_capture_id in payment_captures."""
    session = ShoppingSession(session_identifier="guest_sess_uniq_cap")
    test_session.add(session)
    test_session.commit()

    order = PaymentOrder(
        session_id=session.id,
        paypal_order_id="PAYPAL-ORDER-FOR-CAP-1",
        total_amount=Decimal("100.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order)
    test_session.commit()

    cap1 = PaymentCapture(
        payment_order_id=order.id,
        paypal_order_id="PAYPAL-ORDER-FOR-CAP-1",
        paypal_capture_id="CAP-DUPLICATE-999",
        captured_amount=Decimal("100.00"),
        currency="USD",
    )
    test_session.add(cap1)
    test_session.commit()

    cap2 = PaymentCapture(
        payment_order_id=order.id,
        paypal_order_id="PAYPAL-ORDER-FOR-CAP-1",
        paypal_capture_id="CAP-DUPLICATE-999",  # Duplicate!
        captured_amount=Decimal("100.00"),
        currency="USD",
    )
    test_session.add(cap2)
    with pytest.raises(IntegrityError):
        test_session.commit()
    test_session.rollback()


def test_unique_paypal_request_id_constraint(test_session: Session):
    """Enforce uniqueness constraint on paypal_request_id."""
    session = ShoppingSession(session_identifier="guest_sess_uniq_req_id")
    test_session.add(session)
    test_session.commit()

    order1 = PaymentOrder(
        session_id=session.id,
        paypal_request_id="REQ-UUID-COLLISION-TEST",
        total_amount=Decimal("20.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order1)
    test_session.commit()

    order2 = PaymentOrder(
        session_id=session.id,
        paypal_request_id="REQ-UUID-COLLISION-TEST",  # Duplicate!
        total_amount=Decimal("30.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order2)
    with pytest.raises(IntegrityError):
        test_session.commit()
    test_session.rollback()


def test_unique_internal_order_number_constraint(test_session: Session):
    """Enforce uniqueness constraint on internal_order_number."""
    session = ShoppingSession(session_identifier="guest_sess_uniq_ord_no")
    test_session.add(session)
    test_session.commit()

    order1 = PaymentOrder(
        session_id=session.id,
        internal_order_number="ORD-20261102-COLLISION",
        total_amount=Decimal("20.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order1)
    test_session.commit()

    order2 = PaymentOrder(
        session_id=session.id,
        internal_order_number="ORD-20261102-COLLISION",  # Duplicate!
        total_amount=Decimal("30.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order2)
    with pytest.raises(IntegrityError):
        test_session.commit()
    test_session.rollback()


# =============================================================================
# Category 5: Currency Preservation & Exact Decimal Precision
# =============================================================================

def test_currency_preservation_and_exact_decimal_precision(test_session: Session):
    """Verify exact Decimal representation without floating point inaccuracy across currencies."""
    session = ShoppingSession(session_identifier="guest_sess_currency_decimal")
    test_session.add(session)
    test_session.commit()

    usd_order = PaymentOrder(
        session_id=session.id,
        total_amount=Decimal("199.95"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    eur_order = PaymentOrder(
        session_id=session.id,
        total_amount=Decimal("89.50"),
        currency="EUR",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    inr_order = PaymentOrder(
        session_id=session.id,
        total_amount=Decimal("74999.00"),
        currency="INR",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add_all([usd_order, eur_order, inr_order])
    test_session.commit()

    q_usd = test_session.query(PaymentOrder).filter_by(id=usd_order.id).first()
    assert isinstance(q_usd.total_amount, Decimal)
    assert q_usd.total_amount == Decimal("199.95")
    assert q_usd.currency == "USD"

    q_eur = test_session.query(PaymentOrder).filter_by(id=eur_order.id).first()
    assert isinstance(q_eur.total_amount, Decimal)
    assert q_eur.total_amount == Decimal("89.50")
    assert q_eur.currency == "EUR"

    q_inr = test_session.query(PaymentOrder).filter_by(id=inr_order.id).first()
    assert isinstance(q_inr.total_amount, Decimal)
    assert q_inr.total_amount == Decimal("74999.00")
    assert q_inr.currency == "INR"


# =============================================================================
# Category 6: Payment Lifecycle State Transitions
# =============================================================================

def test_valid_payment_order_lifecycle_happy_path(test_session: Session):
    """Verify happy-path transition: CREATED -> APPROVED -> CAPTURE_PENDING -> COMPLETED."""
    session = ShoppingSession(session_identifier="guest_sess_lifecycle_happy")
    test_session.add(session)
    test_session.commit()

    order = PaymentOrder(
        session_id=session.id,
        total_amount=Decimal("100.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order)
    test_session.commit()

    assert order.status == PaymentOrderStatus.CREATED.value

    # 1. User approves on PayPal
    assert order.can_transition_to(PaymentOrderStatus.APPROVED) is True
    order.transition_to(PaymentOrderStatus.APPROVED)
    assert order.status == PaymentOrderStatus.APPROVED.value

    # 2. Backend initiates capture
    assert order.can_transition_to(PaymentOrderStatus.CAPTURE_PENDING) is True
    order.transition_to(PaymentOrderStatus.CAPTURE_PENDING)
    assert order.status == PaymentOrderStatus.CAPTURE_PENDING.value

    # 3. Capture verified & completed via trusted verification
    assert order.can_transition_to(PaymentOrderStatus.COMPLETED) is True
    capture = PaymentCapture(
        payment_order_id=order.id,
        paypal_order_id="5O190127TN364715T",
        paypal_capture_id="CAP-HAPPY-PATH-1",
        captured_amount=Decimal("100.00"),
        currency="USD",
        capture_status="COMPLETED",
        is_verified=True,
    )
    order.complete_with_verified_capture(capture)
    assert order.status == PaymentOrderStatus.COMPLETED.value


def test_valid_cancellation_and_expiry_lifecycle(test_session: Session):
    """Verify cancellation, expiry, and failure paths from CREATED and APPROVED."""
    session = ShoppingSession(session_identifier="guest_sess_lifecycle_branches")
    test_session.add(session)
    test_session.commit()

    # Cancelled directly from CREATED
    order_cancel = PaymentOrder(
        session_id=session.id,
        total_amount=Decimal("50.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    order_cancel.transition_to(PaymentOrderStatus.CANCELLED)
    assert order_cancel.status == PaymentOrderStatus.CANCELLED.value

    # Expired from CREATED
    order_expire = PaymentOrder(
        session_id=session.id,
        total_amount=Decimal("60.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    order_expire.transition_to(PaymentOrderStatus.EXPIRED)
    assert order_expire.status == PaymentOrderStatus.EXPIRED.value
    assert order_expire.is_expired is True

    # Failed from CREATED
    order_fail = PaymentOrder(
        session_id=session.id,
        total_amount=Decimal("70.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    order_fail.transition_to(PaymentOrderStatus.FAILED)
    assert order_fail.status == PaymentOrderStatus.FAILED.value

    # Cancelled from APPROVED
    order_approved_cancel = PaymentOrder(
        session_id=session.id,
        total_amount=Decimal("80.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    order_approved_cancel.transition_to(PaymentOrderStatus.APPROVED)
    order_approved_cancel.transition_to(PaymentOrderStatus.CANCELLED)
    assert order_approved_cancel.status == PaymentOrderStatus.CANCELLED.value


def test_invalid_payment_state_transitions_rejected():
    """Verify that illegal transitions raise InvalidStateTransitionError."""
    order = PaymentOrder(
        session_id="dummy_sess",
        total_amount=Decimal("100.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    assert order.status == PaymentOrderStatus.CREATED.value

    # 1. Illegal shortcut: CREATED directly to COMPLETED
    assert order.can_transition_to(PaymentOrderStatus.COMPLETED) is False
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        order.transition_to(PaymentOrderStatus.COMPLETED)
    assert "Cannot transition PaymentOrder from 'CREATED' to 'COMPLETED'" in str(exc_info.value)

    # 2. Illegal shortcut: CREATED directly to CAPTURE_PENDING (skipping approval)
    assert order.can_transition_to(PaymentOrderStatus.CAPTURE_PENDING) is False
    with pytest.raises(InvalidStateTransitionError):
        order.transition_to(PaymentOrderStatus.CAPTURE_PENDING)

    # 3. Illegal shortcut: APPROVED directly to COMPLETED (skipping capture pending)
    order.transition_to(PaymentOrderStatus.APPROVED)
    assert order.can_transition_to(PaymentOrderStatus.COMPLETED) is False
    with pytest.raises(InvalidStateTransitionError):
        order.transition_to(PaymentOrderStatus.COMPLETED)

    # 4. Terminal states cannot transition to anything
    order.transition_to(PaymentOrderStatus.CAPTURE_PENDING)
    capture = PaymentCapture(
        payment_order_id=order.id,
        paypal_order_id="5O190127TN364715T",
        paypal_capture_id="CAP-TERM-CHECK-1",
        captured_amount=Decimal("100.00"),
        currency="USD",
        capture_status="COMPLETED",
        is_verified=True,
    )
    order.complete_with_verified_capture(capture)
    assert order.status == PaymentOrderStatus.COMPLETED.value

    for target in [PaymentOrderStatus.CREATED, PaymentOrderStatus.APPROVED, PaymentOrderStatus.CANCELLED, PaymentOrderStatus.FAILED]:
        assert order.can_transition_to(target) is False
        with pytest.raises(InvalidStateTransitionError):
            order.transition_to(target)


# =============================================================================
# Category 7: Foreign Key Integrity Constraints
# =============================================================================

def test_foreign_key_session_integrity(test_session: Session):
    """Enforce foreign key constraint: session_id must exist in shopping_sessions."""
    order = PaymentOrder(
        session_id="non-existent-session-uuid",
        total_amount=Decimal("50.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order)
    with pytest.raises(IntegrityError):
        test_session.commit()
    test_session.rollback()


def test_foreign_key_order_item_integrity(test_session: Session):
    """Enforce foreign key constraint: payment_order_id must exist in payment_orders."""
    item = OrderItem(
        payment_order_id="non-existent-order-uuid",
        product_name="Fake Item",
        quantity=1,
        unit_price=Decimal("10.00"),
        subtotal=Decimal("10.00"),
        currency="USD",
    )
    test_session.add(item)
    with pytest.raises(IntegrityError):
        test_session.commit()
    test_session.rollback()


def test_foreign_key_capture_integrity(test_session: Session):
    """Enforce foreign key constraint: payment_order_id must exist for PaymentCapture."""
    capture = PaymentCapture(
        payment_order_id="non-existent-order-uuid",
        paypal_order_id="PP-NON-EXISTENT",
        paypal_capture_id="CAP-NON-EXISTENT",
        captured_amount=Decimal("100.00"),
        currency="USD",
    )
    test_session.add(capture)
    with pytest.raises(IntegrityError):
        test_session.commit()
    test_session.rollback()


def test_foreign_key_restrict_on_product_deletion(test_session: Session):
    """Enforce ON DELETE RESTRICT on product_id so historical order items are protected."""
    session = ShoppingSession(session_identifier="guest_sess_fk_restrict")
    test_session.add(session)
    test_session.commit()

    prod = Product(
        name="Historical Camera",
        brand="Nikon",
        category="Electronics",
        description="DSLR Camera",
    )
    test_session.add(prod)
    test_session.commit()

    order = PaymentOrder(
        session_id=session.id,
        total_amount=Decimal("699.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order)
    test_session.commit()

    item = OrderItem(
        payment_order_id=order.id,
        product_id=prod.id,
        product_name="Historical Camera",
        quantity=1,
        unit_price=Decimal("699.00"),
        subtotal=Decimal("699.00"),
        currency="USD",
    )
    test_session.add(item)
    test_session.commit()

    # Attempt to delete Product: should be RESTRICTED by foreign key
    test_session.delete(prod)
    with pytest.raises(IntegrityError):
        test_session.commit()
    test_session.rollback()


# =============================================================================
# Category 8: Pydantic v2 Schemas Validation
# =============================================================================

def test_pydantic_checkout_schemas():
    """Verify CheckoutOrderCreate and response schemas validate properly."""
    payload = {
        "session_identifier": "test_guest_cookie_123",
        "currency": "USD",
        "items": [
            {
                "product_name": "Mechanical Keyboard",
                "quantity": 2,
                "unit_price": "89.99",
                "currency": "USD",
                "retailer_name": "Keychron",
            }
        ],
    }
    create_schema = CheckoutOrderCreate.model_validate(payload)
    assert len(create_schema.items) == 1
    assert create_schema.items[0].quantity == 2
    assert create_schema.items[0].unit_price == Decimal("89.99")
    assert isinstance(create_schema.items[0].unit_price, Decimal)


def test_pydantic_schema_rejects_negative_or_zero_price():
    """Verify that schemas enforce positive unit_price."""
    invalid_payload = {
        "items": [
            {
                "product_name": "Free item",
                "quantity": 1,
                "unit_price": "0.00",
                "currency": "USD",
            }
        ]
    }
    with pytest.raises(ValueError):
        CheckoutOrderCreate.model_validate(invalid_payload)


def test_pydantic_schema_from_orm_models(test_session: Session):
    """Verify PaymentOrderResponse and OrderItemResponse serialize from ORM models."""
    session = ShoppingSession(session_identifier="guest_sess_orm_pydantic")
    test_session.add(session)
    test_session.commit()

    order = PaymentOrder(
        session_id=session.id,
        paypal_order_id="5O190127TN364715T",
        total_amount=Decimal("120.50"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order)
    test_session.commit()

    item = OrderItem(
        payment_order_id=order.id,
        product_name="USB-C Hub",
        quantity=1,
        unit_price=Decimal("120.50"),
        subtotal=Decimal("120.50"),
        currency="USD",
    )
    test_session.add(item)
    test_session.commit()

    # Re-query
    queried = test_session.query(PaymentOrder).filter_by(id=order.id).first()
    pydantic_order = PaymentOrderResponse.model_validate(queried)
    assert pydantic_order.id == order.id
    assert pydantic_order.total_amount == Decimal("120.50")
    assert pydantic_order.currency == "USD"
    assert len(pydantic_order.items) == 1
    assert pydantic_order.items[0].product_name == "USB-C Hub"
    assert pydantic_order.items[0].subtotal == Decimal("120.50")


def test_payment_history_summary_schema():
    """Verify PaymentHistoryItemResponse schema."""
    history_item = PaymentHistoryItemResponse(
        id="ord_uuid_123",
        internal_order_number="ORD-20261102-8F3A29B1",
        status="COMPLETED",
        total_amount=Decimal("299.99"),
        currency="USD",
        item_count=1,
        paypal_order_id="5O190127TN364715T",
        paypal_capture_id="CAP-12345678",
        created_at=datetime.now(timezone.utc),
        captured_at=datetime.now(timezone.utc),
    )
    assert history_item.internal_order_number == "ORD-20261102-8F3A29B1"
    assert history_item.total_amount == Decimal("299.99")
    assert history_item.item_count == 1


# =============================================================================
# Category 9: Phase 4.1.1 Safety Hardening Tests
# =============================================================================

def test_session_deletion_preserves_payment_order_history(test_session: Session):
    """
    Safety Hardening Invariant 1:
    Deleting a ShoppingSession must NEVER delete PaymentOrder, OrderItem, or PaymentCapture.
    Instead, session_id is safely set to NULL (ON DELETE SET NULL) preserving the financial ledger.
    """
    session = ShoppingSession(session_identifier="guest_sess_to_be_purged")
    test_session.add(session)
    test_session.commit()

    prod = Product(
        name="Audit Preserved Headphone",
        brand="Sony",
        category="Electronics",
        description="Preserved product",
    )
    test_session.add(prod)
    test_session.commit()

    order = PaymentOrder(
        session_id=session.id,
        internal_order_number="ORD-AUDIT-PRESERVE-001",
        total_amount=Decimal("349.99"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order)
    test_session.commit()

    item = OrderItem(
        payment_order_id=order.id,
        product_id=prod.id,
        product_name="Audit Preserved Headphone",
        quantity=1,
        unit_price=Decimal("349.99"),
        subtotal=Decimal("349.99"),
        currency="USD",
    )
    capture = PaymentCapture(
        payment_order_id=order.id,
        paypal_order_id="PP-ORD-AUDIT-1",
        paypal_capture_id="CAP-AUDIT-1",
        captured_amount=Decimal("349.99"),
        currency="USD",
        is_verified=True,
    )
    test_session.add_all([item, capture])
    test_session.commit()

    order_id = order.id
    item_id = item.id
    capture_id = capture.id

    # Delete the guest ShoppingSession
    test_session.delete(session)
    test_session.commit()

    # Verify that the session is gone
    assert test_session.query(ShoppingSession).filter_by(id=session.id).first() is None

    # CRITICAL CHECK: PaymentOrder MUST still exist!
    preserved_order = test_session.query(PaymentOrder).filter_by(id=order_id).first()
    assert preserved_order is not None
    assert preserved_order.session_id is None  # Safely set to NULL
    assert preserved_order.total_amount == Decimal("349.99")
    assert preserved_order.internal_order_number == "ORD-AUDIT-PRESERVE-001"

    # CRITICAL CHECK: OrderItem and PaymentCapture MUST still exist!
    preserved_item = test_session.query(OrderItem).filter_by(id=item_id).first()
    assert preserved_item is not None
    assert preserved_item.product_name == "Audit Preserved Headphone"
    assert preserved_item.subtotal == Decimal("349.99")

    preserved_capture = test_session.query(PaymentCapture).filter_by(id=capture_id).first()
    assert preserved_capture is not None
    assert preserved_capture.paypal_capture_id == "CAP-AUDIT-1"
    assert preserved_capture.captured_amount == Decimal("349.99")


def test_idempotency_keys_across_different_sessions(test_session: Session):
    """
    Safety Hardening Invariant 2:
    Idempotency keys must be scoped to the session.
    Reusing the same key in a different session must succeed.
    """
    session_a = ShoppingSession(session_identifier="guest_sess_idemp_a")
    session_b = ShoppingSession(session_identifier="guest_sess_idemp_b")
    test_session.add_all([session_a, session_b])
    test_session.commit()

    shared_key = "idemp_shared_checkout_key_123"

    order_a = PaymentOrder(
        session_id=session_a.id,
        idempotency_key=shared_key,
        total_amount=Decimal("100.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    order_b = PaymentOrder(
        session_id=session_b.id,
        idempotency_key=shared_key,  # Same key, DIFFERENT session!
        total_amount=Decimal("200.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add_all([order_a, order_b])
    test_session.commit()  # Must succeed!

    assert test_session.query(PaymentOrder).filter_by(id=order_a.id).first() is not None
    assert test_session.query(PaymentOrder).filter_by(id=order_b.id).first() is not None


def test_duplicate_idempotency_within_same_session_rejected(test_session: Session):
    """
    Safety Hardening Invariant 3:
    Reusing the same idempotency key within the SAME session must violate the unique constraint.
    """
    session = ShoppingSession(session_identifier="guest_sess_idemp_collision")
    test_session.add(session)
    test_session.commit()

    duplicate_key = "idemp_same_sess_collision_key"

    order1 = PaymentOrder(
        session_id=session.id,
        idempotency_key=duplicate_key,
        total_amount=Decimal("50.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order1)
    test_session.commit()

    order2 = PaymentOrder(
        session_id=session.id,
        idempotency_key=duplicate_key,  # Duplicate in SAME session!
        total_amount=Decimal("75.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    test_session.add(order2)
    with pytest.raises(IntegrityError):
        test_session.commit()
    test_session.rollback()


def test_capture_amount_mismatch_rejected():
    """
    Safety Hardening Invariant 4:
    A capture with an amount that does not match the order total must be rejected.
    """
    order = PaymentOrder(
        session_id="dummy_sess",
        total_amount=Decimal("150.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    order.transition_to(PaymentOrderStatus.APPROVED)
    order.transition_to(PaymentOrderStatus.CAPTURE_PENDING)

    # Capture amount $100.00 != Order total $150.00
    mismatched_capture = PaymentCapture(
        payment_order_id=order.id,
        paypal_order_id="PP-MISMATCH-AMT",
        paypal_capture_id="CAP-MISMATCH-AMT",
        captured_amount=Decimal("100.00"),
        currency="USD",
        is_verified=True,
    )
    with pytest.raises(CaptureAmountMismatchError) as exc_info:
        order.complete_with_verified_capture(mismatched_capture)
    assert "Capture amount mismatch" in str(exc_info.value)
    assert order.status == PaymentOrderStatus.CAPTURE_PENDING.value


def test_capture_currency_mismatch_rejected():
    """
    Safety Hardening Invariant 5:
    A capture with a currency that does not match the order currency must be rejected.
    """
    order = PaymentOrder(
        session_id="dummy_sess",
        total_amount=Decimal("100.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    order.transition_to(PaymentOrderStatus.APPROVED)
    order.transition_to(PaymentOrderStatus.CAPTURE_PENDING)

    # Capture currency EUR != Order currency USD
    mismatched_currency_capture = PaymentCapture(
        payment_order_id=order.id,
        paypal_order_id="PP-MISMATCH-CURR",
        paypal_capture_id="CAP-MISMATCH-CURR",
        captured_amount=Decimal("100.00"),
        currency="EUR",
        is_verified=True,
    )
    with pytest.raises(CaptureCurrencyMismatchError) as exc_info:
        order.complete_with_verified_capture(mismatched_currency_capture)
    assert "Capture currency mismatch" in str(exc_info.value)
    assert order.status == PaymentOrderStatus.CAPTURE_PENDING.value


def test_unverified_capture_completion_rejected():
    """
    Safety Hardening Invariant 6:
    An unverified capture (is_verified == False) cannot authorize order completion.
    """
    order = PaymentOrder(
        session_id="dummy_sess",
        total_amount=Decimal("100.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    order.transition_to(PaymentOrderStatus.APPROVED)
    order.transition_to(PaymentOrderStatus.CAPTURE_PENDING)

    unverified_capture = PaymentCapture(
        payment_order_id=order.id,
        paypal_order_id="PP-UNVERIFIED",
        paypal_capture_id="CAP-UNVERIFIED",
        captured_amount=Decimal("100.00"),
        currency="USD",
        is_verified=False,  # NOT verified!
    )
    with pytest.raises(UnverifiedCaptureError) as exc_info:
        order.complete_with_verified_capture(unverified_capture)
    assert "has not been independently verified" in str(exc_info.value)
    assert order.status == PaymentOrderStatus.CAPTURE_PENDING.value


def test_direct_completion_without_verified_capture_rejected():
    """
    Safety Hardening Invariant 7:
    Direct transition_to('COMPLETED') without verified capture proof is strictly prohibited.
    """
    order = PaymentOrder(
        session_id="dummy_sess",
        total_amount=Decimal("100.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    order.transition_to(PaymentOrderStatus.APPROVED)
    order.transition_to(PaymentOrderStatus.CAPTURE_PENDING)

    with pytest.raises(InvalidStateTransitionError) as exc_info:
        order.transition_to(PaymentOrderStatus.COMPLETED)
    assert "Direct transition to 'COMPLETED' is prohibited" in str(exc_info.value)
    assert order.status == PaymentOrderStatus.CAPTURE_PENDING.value


def test_terminal_state_immutability_all_terminal_states():
    """
    Safety Hardening Invariant 8:
    Terminal states (COMPLETED, CANCELLED, EXPIRED, FAILED) are strictly immutable.
    """
    # 1. Test COMPLETED immutability
    completed_order = PaymentOrder(
        session_id="dummy_sess",
        total_amount=Decimal("100.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    completed_order.transition_to(PaymentOrderStatus.APPROVED)
    completed_order.transition_to(PaymentOrderStatus.CAPTURE_PENDING)
    valid_capture = PaymentCapture(
        payment_order_id=completed_order.id,
        paypal_order_id="PP-ORD-IMMUTABLE",
        paypal_capture_id="CAP-IMMUTABLE",
        captured_amount=Decimal("100.00"),
        currency="USD",
        is_verified=True,
    )
    completed_order.complete_with_verified_capture(valid_capture)
    assert completed_order.status == PaymentOrderStatus.COMPLETED.value

    for target in [PaymentOrderStatus.CREATED, PaymentOrderStatus.APPROVED, PaymentOrderStatus.CAPTURE_PENDING, PaymentOrderStatus.CANCELLED, PaymentOrderStatus.EXPIRED, PaymentOrderStatus.FAILED]:
        assert completed_order.can_transition_to(target) is False
        with pytest.raises(InvalidStateTransitionError):
            completed_order.transition_to(target)

    # 2. Test CANCELLED immutability
    cancelled_order = PaymentOrder(
        session_id="dummy_sess",
        total_amount=Decimal("100.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    cancelled_order.transition_to(PaymentOrderStatus.CANCELLED)
    for target in [PaymentOrderStatus.CREATED, PaymentOrderStatus.APPROVED, PaymentOrderStatus.CAPTURE_PENDING, PaymentOrderStatus.COMPLETED]:
        assert cancelled_order.can_transition_to(target) is False
        with pytest.raises(InvalidStateTransitionError):
            cancelled_order.transition_to(target)

    # 3. Test EXPIRED immutability
    expired_order = PaymentOrder(
        session_id="dummy_sess",
        total_amount=Decimal("100.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    expired_order.transition_to(PaymentOrderStatus.EXPIRED)
    for target in [PaymentOrderStatus.CREATED, PaymentOrderStatus.APPROVED, PaymentOrderStatus.CAPTURE_PENDING, PaymentOrderStatus.COMPLETED]:
        assert expired_order.can_transition_to(target) is False
        with pytest.raises(InvalidStateTransitionError):
            expired_order.transition_to(target)

    # 4. Test FAILED immutability
    failed_order = PaymentOrder(
        session_id="dummy_sess",
        total_amount=Decimal("100.00"),
        currency="USD",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    failed_order.transition_to(PaymentOrderStatus.FAILED)
    for target in [PaymentOrderStatus.CREATED, PaymentOrderStatus.APPROVED, PaymentOrderStatus.CAPTURE_PENDING, PaymentOrderStatus.COMPLETED]:
        assert failed_order.can_transition_to(target) is False
        with pytest.raises(InvalidStateTransitionError):
            failed_order.transition_to(target)
