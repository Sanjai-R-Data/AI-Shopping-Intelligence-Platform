"""
AI-Powered Multilingual Shopping Intelligence Platform
Channel3 Live Product Aggregation HTTP Client.
Connects securely to Channel3 REST API with timeout control, structured error handling, and zero secret leakage.
"""

import logging
from typing import Any
import httpx

from backend.app.core.config import get_settings

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------
# Channel3 Provider Exception Hierarchy
# -------------------------------------------------------------------------

class Channel3Error(Exception):
    """Base exception for all Channel3 provider errors."""
    pass


class Channel3AuthError(Channel3Error):
    """Raised when Channel3 API key is missing, invalid, or rejected (401/403)."""
    pass


class Channel3RateLimitError(Channel3Error):
    """Raised when Channel3 rate limit / credit quota is exceeded (429)."""

    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class Channel3TimeoutError(Channel3Error):
    """Raised when a Channel3 request exceeds the configured network timeout."""
    pass


class Channel3ServerError(Channel3Error):
    """Raised when Channel3 returns a 5xx server-side error."""
    pass


class Channel3APIError(Channel3Error):
    """Raised when Channel3 returns a generic client/request error (4xx)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class Channel3ResponseError(Channel3Error):
    """Raised when the provider response is invalid or unparseable JSON."""
    pass


# -------------------------------------------------------------------------
# Channel3 HTTP Client
# -------------------------------------------------------------------------

class Channel3Client:
    """
    HTTP client for interacting with the Channel3 Product Aggregation API.
    Enforces credit protection: no bulk searches, no automated retry storms, minimal query limits.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key: str | None = (
            api_key
            if api_key is not None
            else (settings.CHANNEL3_API_KEY.get_secret_value() if settings.CHANNEL3_API_KEY else None)
        )
        self.base_url: str = (base_url or settings.CHANNEL3_BASE_URL).rstrip("/")
        self.timeout: float = timeout or settings.CHANNEL3_TIMEOUT_SECONDS

    @property
    def is_configured(self) -> bool:
        """Return True if an API key is available."""
        return bool(self._api_key and self._api_key.strip())

    def _get_headers(self) -> dict[str, str]:
        """Build safe request headers. Never logs or leaks the key."""
        if not self.is_configured:
            raise Channel3AuthError("Channel3 API key is not configured in settings or environment.")
        return {
            "x-api-key": self._api_key,  # type: ignore[dict-item]
            "Content-Type": "application/json",
            "User-Agent": "AI-Shopping-Platform/0.1.0",
        }

    def search_products(
        self,
        query: str,
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a live product search against Channel3 (POST /v1/search).
        
        Args:
            query: Natural language product search string.
            limit: Maximum products to retrieve (1-30, default 10).
            filters: Optional dictionary of search filters.
            
        Returns:
            Dictionary containing 'products' list and optional 'next_page_token'.
        """
        if not query or not query.strip():
            return {"products": [], "next_page_token": None}

        clean_limit = max(1, min(limit, 30))
        url = f"{self.base_url}/v1/search"
        headers = self._get_headers()
        payload: dict[str, Any] = {
            "query": query.strip(),
            "limit": clean_limit,
        }
        if filters:
            payload["filters"] = filters

        logger.info("Executing Channel3 product search (query='%s', limit=%d)", query.strip(), clean_limit)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            logger.warning("Channel3 product search timed out after %.1fs for query='%s'", self.timeout, query)
            raise Channel3TimeoutError(f"Channel3 request timed out after {self.timeout}s.") from exc
        except httpx.RequestError as exc:
            logger.error("Channel3 network connection error for query='%s': %s", query, str(exc))
            raise Channel3APIError(f"Failed to connect to Channel3 API: {exc}") from exc

        return self._handle_response(response, operation="search")

    def get_product_by_id(self, product_id: str) -> dict[str, Any] | None:
        """
        Fetch full product details and fresh offers by Channel3 product ID (GET /v1/products/{id}).
        This endpoint is free per Channel3 documentation and recommended for offer revalidation.
        """
        if not product_id or not product_id.strip():
            return None

        clean_id = product_id.strip()
        url = f"{self.base_url}/v1/products/{clean_id}"
        headers = self._get_headers()

        logger.info("Fetching Channel3 product details (id='%s')", clean_id)

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=headers)
        except httpx.TimeoutException as exc:
            logger.warning("Channel3 product lookup timed out for id='%s'", clean_id)
            raise Channel3TimeoutError(f"Channel3 lookup timed out for product '{clean_id}'.") from exc
        except httpx.RequestError as exc:
            logger.error("Channel3 lookup network error for id='%s': %s", clean_id, str(exc))
            raise Channel3APIError(f"Failed to connect to Channel3 lookup: {exc}") from exc

        if response.status_code == 404:
            return None

        return self._handle_response(response, operation="lookup")

    def _handle_response(self, response: httpx.Response, operation: str) -> dict[str, Any]:
        """Inspect HTTP status codes, log sanitized metadata, and parse JSON payload."""
        status = response.status_code
        logger.info("Channel3 %s response: status=%d", operation, status)

        if status == 200:
            try:
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("Root response is not a JSON object")
                return data
            except Exception as exc:
                logger.error("Invalid JSON from Channel3: %s", str(exc))
                raise Channel3ResponseError("Malformed JSON response from Channel3 API.") from exc

        if status in (401, 403):
            logger.error("Channel3 authentication failed with status %d", status)
            raise Channel3AuthError(f"Channel3 authentication failed (HTTP {status}). Verify API key.")

        if status == 429:
            retry_after_str = response.headers.get("Retry-After")
            retry_after = int(retry_after_str) if retry_after_str and retry_after_str.isdigit() else None
            logger.warning("Channel3 rate limit exceeded (HTTP 429, Retry-After=%s)", retry_after_str)
            raise Channel3RateLimitError("Channel3 rate limit or quota exceeded.", retry_after=retry_after)

        if 500 <= status < 600:
            logger.error("Channel3 upstream server error (HTTP %d): %s", status, response.text[:200])
            raise Channel3ServerError(f"Channel3 upstream service unavailable (HTTP {status}).")

        logger.error("Channel3 client error (HTTP %d): %s", status, response.text[:200])
        raise Channel3APIError(f"Channel3 request failed with status {status}.", status_code=status)
