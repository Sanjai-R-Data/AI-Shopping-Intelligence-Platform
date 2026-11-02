"""
AI-Powered Multilingual Shopping Intelligence Platform
Assistant API Router.
Provides conversational AI endpoints for natural language shopping queries,
orchestrating Gemini intent extraction, Channel3 product retrieval, and Spending Mandate compliance.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.schemas.assistant import AssistantQueryRequest, AssistantQueryResponse
from backend.app.services.assistant_service import AssistantService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assistant", tags=["Assistant"])


@router.post(
    "/query",
    response_model=AssistantQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Process conversational shopping assistant query",
    description=(
        "Accepts a natural-language shopping query in English or multilingual languages, "
        "extracts shopping intent via Gemini, fetches live products, evaluates spending mandates, "
        "and synthesizes grounded product recommendations."
    ),
)
def query_assistant(
    request: AssistantQueryRequest,
    db: Session = Depends(get_db),
) -> AssistantQueryResponse:
    """
    Process a user query through the AI Assistant pipeline:
    1. Intent extraction with structured schema (Gemini or deterministic fallback).
    2. Backend-controlled product aggregation (Channel3 or stored catalog).
    3. Authoritative deterministic spending mandate policy check.
    4. Grounded AI product intelligence & comparative synthesis.
    """
    try:
        response = AssistantService.process_query(db=db, request=request)
        return response
    except Exception as exc:
        logger.exception("Unexpected error in assistant query processing: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Assistant failed to process query: {str(exc)}",
        ) from exc
