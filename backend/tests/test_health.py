"""
AI-Powered Multilingual Shopping Intelligence Platform
System & Health Endpoint Tests.
Verifies root endpoint, live database health probe, failure detection, and RFC 9457 error contracts.
"""

from unittest.mock import MagicMock
import pytest
import httpx
from fastapi import status
from sqlalchemy.orm import Session

from backend.app.main import app
from backend.app.core.database import get_db
from backend.app.core.errors import PROBLEM_CONTENT_TYPE


@pytest.mark.asyncio
async def test_root_endpoint_success(async_client: httpx.AsyncClient):
    """
    Test 1: Root endpoint (GET /) returns successfully with application metadata.
    """
    response = await async_client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers.get("content-type") == "application/json"

    data = response.json()
    assert data["status"] == "running"
    assert "AI-Powered Multilingual Shopping Intelligence Platform" in data["app"]
    assert data["docs_url"] == "/docs"
    assert data["health_url"] == "/health"
    assert "version" in data
    assert "environment" in data


@pytest.mark.asyncio
async def test_health_endpoint_success(async_client: httpx.AsyncClient):
    """
    Test 2: Health endpoint (GET /health) succeeds and confirms live database connectivity.
    """
    response = await async_client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.headers.get("content-type") == "application/json"

    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "app" in data
    assert "version" in data
    assert "environment" in data


@pytest.mark.asyncio
async def test_health_endpoint_db_failure_detection():
    """
    Test 3: Health endpoint detects database connectivity failure.
    Must return HTTP 503 and RFC 9457 Problem Details when DB probe fails.
    """
    # Create mock session where execute raises an operational database error
    mock_failing_session = MagicMock(spec=Session)
    mock_failing_session.execute.side_effect = Exception("Connection refused / database unreachable")

    def _failing_get_db():
        yield mock_failing_session

    app.dependency_overrides[get_db] = _failing_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    app.dependency_overrides.clear()

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.headers.get("content-type") == PROBLEM_CONTENT_TYPE

    data = response.json()
    assert data["status"] == 503
    assert data["title"] == "Service Unavailable"
    assert data["detail"] == "Database connectivity check failed"
    assert data["instance"] == "/health"
    assert "type" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_invalid_request_validation(async_client: httpx.AsyncClient):
    """
    Test 4: Invalid request produces an appropriate 422 validation response formatted via RFC 9457.
    """
    # check_timeout parameter must be an integer between 1 and 60
    response = await async_client.get("/health?check_timeout=not-a-number")

    status_422 = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)
    assert response.status_code == status_422
    assert response.headers.get("content-type") == PROBLEM_CONTENT_TYPE

    data = response.json()
    assert data["status"] == 422
    assert data["title"] == "Unprocessable Entity"
    assert data["instance"] == "/health"
    assert data["code"] == "REQUEST_VALIDATION_FAILED"
    assert "invalid_params" in data
    assert len(data["invalid_params"]) >= 1
    assert "check_timeout" in data["invalid_params"][0]["name"]


@pytest.mark.asyncio
async def test_rfc9457_problem_details_not_found(async_client: httpx.AsyncClient):
    """
    Test 5: Error responses follow RFC 9457 Problem Details format for 404 Not Found.
    """
    response = await async_client.get("/non-existent-endpoint-path")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.headers.get("content-type") == PROBLEM_CONTENT_TYPE

    data = response.json()
    assert data["type"] == "about:blank"
    assert data["title"] == "Not Found"
    assert data["status"] == 404
    assert data["instance"] == "/non-existent-endpoint-path"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_rfc9457_internal_server_error_sanitization():
    """
    Test 6: Unexpected application errors return sanitized 500 response without leaking internal details.
    """
    # Simulate an unexpected unhandled exception during route execution
    def _crashing_db():
        raise ValueError("CRITICAL_INTERNAL_DB_PASSWORD_LEAK_TEST_FAILURE")

    app.dependency_overrides[get_db] = _crashing_db

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    app.dependency_overrides.clear()

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.headers.get("content-type") == PROBLEM_CONTENT_TYPE

    data = response.json()
    assert data["status"] == 500
    assert data["title"] == "Internal Server Error"
    # Verify that the internal exception message is strictly stripped and not leaked
    assert "CRITICAL_INTERNAL_DB_PASSWORD" not in str(data)
    assert data["detail"] == "An unexpected internal server error occurred. Please try again later."
    assert data["code"] == "INTERNAL_SERVER_ERROR"
