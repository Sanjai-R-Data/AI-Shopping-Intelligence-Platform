"""
AI-Powered Multilingual Shopping Intelligence Platform
Spending Mandate & Policy Validation API Endpoints.
Routes:
  POST /api/mandates               - Create or configure spending mandate
  GET  /api/mandates/{session_id}  - Retrieve active spending mandate
  PUT  /api/mandates/{session_id}  - Update spending mandate configuration
  POST /api/mandates/{session_id}/validate - Deterministic purchase policy verification
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.repositories.mandate_repository import MandateRepository
from backend.app.schemas.mandate import (
    SpendingMandateCreate,
    SpendingMandateUpdate,
    SpendingMandateResponse,
    PurchaseEvaluationRequest,
    PurchaseEvaluationResponse,
)
from backend.app.services.policy_engine import SpendingPolicyEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mandates", tags=["Spending Mandates"])


@router.post(
    "",
    response_model=SpendingMandateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or Configure Spending Mandate",
    description="Establish a deterministic budget, max item price, and quantity limit for a guest shopping session.",
)
def create_mandate(
    payload: SpendingMandateCreate,
    db: Session = Depends(get_db),
) -> SpendingMandateResponse:
    """Create or configure a session spending mandate."""
    if payload.maximum_item_price > payload.total_budget:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="maximum_item_price cannot exceed total_budget.",
        )

    # Resolve or create the guest session
    session = MandateRepository.get_or_create_session(
        db=db,
        session_id=payload.session_id,
        session_identifier=payload.session_identifier,
    )

    mandate = MandateRepository.create_or_update_mandate(
        db=db,
        session_id=session.id,
        total_budget=payload.total_budget,
        maximum_item_price=payload.maximum_item_price,
        maximum_quantity=payload.maximum_quantity,
        currency=payload.currency,
    )

    return SpendingMandateResponse.model_validate(mandate)


@router.get(
    "/{session_id}",
    response_model=SpendingMandateResponse,
    summary="Retrieve Active Spending Mandate",
    description="Retrieve the configured spending mandate for a given session ID.",
)
def get_mandate(
    session_id: str,
    db: Session = Depends(get_db),
) -> SpendingMandateResponse:
    """Fetch active mandate for session."""
    mandate = MandateRepository.get_mandate_by_session_id(db, session_id)
    if not mandate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No spending mandate found for session '{session_id}'.",
        )
    return SpendingMandateResponse.model_validate(mandate)


@router.put(
    "/{session_id}",
    response_model=SpendingMandateResponse,
    summary="Update Spending Mandate",
    description="Modify budget ceilings, item price limits, or maximum quantity for a session mandate.",
)
def update_mandate(
    session_id: str,
    payload: SpendingMandateUpdate,
    db: Session = Depends(get_db),
) -> SpendingMandateResponse:
    """Update existing spending mandate."""
    existing = MandateRepository.get_mandate_by_session_id(db, session_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No spending mandate found for session '{session_id}'.",
        )

    # Validate that maximum_item_price does not exceed total_budget after update
    effective_budget = payload.total_budget if payload.total_budget is not None else existing.total_budget
    effective_max_price = payload.maximum_item_price if payload.maximum_item_price is not None else existing.maximum_item_price
    if effective_max_price > effective_budget:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="maximum_item_price cannot exceed total_budget.",
        )

    updated = MandateRepository.update_mandate_fields(
        db=db,
        session_id=session_id,
        total_budget=payload.total_budget,
        maximum_item_price=payload.maximum_item_price,
        maximum_quantity=payload.maximum_quantity,
        currency=payload.currency,
    )

    return SpendingMandateResponse.model_validate(updated)


@router.post(
    "/{session_id}/validate",
    response_model=PurchaseEvaluationResponse,
    summary="Deterministic Policy Purchase Validation",
    description="Evaluate a candidate item purchase against the session's active spending mandate. Returns ALLOWED or BLOCKED.",
)
def validate_purchase(
    session_id: str,
    payload: PurchaseEvaluationRequest,
    db: Session = Depends(get_db),
) -> PurchaseEvaluationResponse:
    """
    Deterministic rule validation endpoint.
    Verifies budget ceiling, item price limits, and quantity restrictions.
    Independent of AI recommendation logic.
    """
    mandate = MandateRepository.get_mandate_by_session_id(db, session_id)

    evaluation = SpendingPolicyEngine.evaluate(
        mandate=mandate,
        unit_price=payload.unit_price,
        quantity=payload.quantity,
        currency=payload.currency,
    )

    return evaluation
