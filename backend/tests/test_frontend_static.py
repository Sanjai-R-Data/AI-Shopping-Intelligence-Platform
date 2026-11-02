"""
BUYWISE AI — Frontend Static Integration & Asset Serving Tests.
Verifies FastAPI serving of index.html, static assets (CSS, JS), route preservation, and error handling.
"""

import httpx
import pytest
from fastapi import status


@pytest.mark.asyncio
async def test_frontend_index_served_for_browser(async_client: httpx.AsyncClient):
    """Verify GET / with browser Accept header returns HTML application shell."""
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    }
    response = await async_client.get("/", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert "text/html" in response.headers.get("content-type", "")
    assert "<!DOCTYPE html>" in response.text
    assert "BUYWISE AI" in response.text
    assert "Discover smarter." in response.text
    assert "Compare deeper." in response.text
    assert "Spend responsibly." in response.text


@pytest.mark.asyncio
async def test_frontend_direct_index_html(async_client: httpx.AsyncClient):
    """Verify GET /index.html returns HTML application shell."""
    response = await async_client.get("/index.html")
    assert response.status_code == status.HTTP_200_OK
    assert "text/html" in response.headers.get("content-type", "")
    assert "BUYWISE AI" in response.text


@pytest.mark.asyncio
async def test_frontend_css_asset_served(async_client: httpx.AsyncClient):
    """Verify /assets/css/styles.css is served with correct mime type."""
    response = await async_client.get("/assets/css/styles.css")
    assert response.status_code == status.HTTP_200_OK
    assert "text/css" in response.headers.get("content-type", "")
    assert "--color-burnt-orange" in response.text


@pytest.mark.asyncio
async def test_frontend_js_modules_served(async_client: httpx.AsyncClient):
    """Verify all JavaScript ES modules are properly served."""
    modules = ["app.js", "api.js", "components.js", "config.js"]
    for mod in modules:
        response = await async_client.get(f"/assets/js/{mod}")
        assert response.status_code == status.HTTP_200_OK
        ctype = response.headers.get("content-type", "")
        assert "javascript" in ctype or "text/plain" in ctype
        assert len(response.text) > 50


@pytest.mark.asyncio
async def test_missing_static_asset_returns_404(async_client: httpx.AsyncClient):
    """Verify missing static file under /assets returns 404 Not Found."""
    response = await async_client.get("/assets/js/non_existent_file.js")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_docs_and_openapi_preserved(async_client: httpx.AsyncClient):
    """Verify OpenAPI documentation routes are not shadowed by frontend mounts."""
    docs_res = await async_client.get("/docs")
    assert docs_res.status_code == status.HTTP_200_OK
    assert "text/html" in docs_res.headers.get("content-type", "")

    openapi_res = await async_client.get("/openapi.json")
    assert openapi_res.status_code == status.HTTP_200_OK
    assert "application/json" in openapi_res.headers.get("content-type", "")
    data = openapi_res.json()
    assert "openapi" in data
    assert "/api/products" in data.get("paths", {})
    assert "/api/mandates" in data.get("paths", {})
    assert "/api/checkout/orders" in data.get("paths", {})


@pytest.mark.asyncio
async def test_favicon_endpoint(async_client: httpx.AsyncClient):
    """Verify GET /favicon.ico returns 204 No Content."""
    response = await async_client.get("/favicon.ico")
    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_frontend_js_exports_and_imports(async_client: httpx.AsyncClient):
    """
    Verify components.js exports safe image helpers and app.js imports them.
    Ensures PLACEHOLDER_IMAGE is never undefined and uses base64 data URI to avoid attribute escapes.
    """
    components_res = await async_client.get("/assets/js/components.js")
    assert components_res.status_code == status.HTTP_200_OK
    c_text = components_res.text

    assert "export const PLACEHOLDER_IMAGE" in c_text
    assert "data:image/svg+xml;base64," in c_text
    assert "export function getSafeImageUrl" in c_text
    assert "export const IMG_FALLBACK_ATTR" in c_text
    assert "export function escapeHtml" in c_text

    app_res = await async_client.get("/assets/js/app.js")
    assert app_res.status_code == status.HTTP_200_OK
    a_text = app_res.text

    assert "PLACEHOLDER_IMAGE" in a_text
    assert "getSafeImageUrl" in a_text
    assert "IMG_FALLBACK_ATTR" in a_text
    assert "escapeHtml" in a_text
    # Ensure no naked unescaped inline SVGs inside onerror
    assert 'onerror="this.onerror=null; this.src=\'data:image/svg+xml' not in a_text


@pytest.mark.asyncio
async def test_seed_products_image_urls_valid(async_client: httpx.AsyncClient):
    """
    Verify all seeded product items returned by the API have valid, non-broken image URLs.
    Specifically checks Apple Watch does not use coffee cup image and Anker Power Bank does not use 404 URL.
    """
    response = await async_client.get("/api/products?page=1&page_size=50")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    items = data.get("items", [])
    assert len(items) > 0

    for item in items:
        img = item.get("image_url")
        assert img is not None and isinstance(img, str) and len(img) > 10
        assert img.startswith("http://") or img.startswith("https://") or img.startswith("data:image/")

        # Verify Apple Watch Series 9 uses watch image (1546868871-7041f2a55e12), not coffee cup (1509042239860)
        if "Apple Watch Series 9" in item.get("name", ""):
            assert "1509042239860" not in img
            assert "1546868871-7041f2a55e12" in img

        # Verify Anker 737 uses working powerbank image (1583863788434-e58a36330cf0), not deleted 404 (1609592426508)
        if "Anker 737" in item.get("name", ""):
            assert "1609592426508" not in img
            assert "1583863788434-e58a36330cf0" in img


@pytest.mark.asyncio
async def test_compare_products_api(async_client: httpx.AsyncClient):
    """
    Verify product comparison API succeeds for 2, 3, and 4 items,
    and returns proper comparison matrix and specs.
    """
    # Fetch first 4 product IDs
    p_res = await async_client.get("/api/products?page=1&page_size=4")
    assert p_res.status_code == status.HTTP_200_OK
    products = p_res.json().get("items", [])
    assert len(products) >= 4
    p_ids = [p["id"] for p in products]

    # Test 2 items
    compare2 = await async_client.get(f"/api/products/compare?ids={p_ids[0]}&ids={p_ids[1]}")
    assert compare2.status_code == status.HTTP_200_OK
    c2_data = compare2.json()
    assert len(c2_data["products"]) == 2
    assert "comparison_matrix" in c2_data
    assert "price_summary" in c2_data

    # Test 3 items
    compare3 = await async_client.get(f"/api/products/compare?ids={p_ids[0]}&ids={p_ids[1]}&ids={p_ids[2]}")
    assert compare3.status_code == status.HTTP_200_OK
    c3_data = compare3.json()
    assert len(c3_data["products"]) == 3

    # Test 4 items
    compare4 = await async_client.get(f"/api/products/compare?ids={p_ids[0]}&ids={p_ids[1]}&ids={p_ids[2]}&ids={p_ids[3]}")
    assert compare4.status_code == status.HTTP_200_OK
    c4_data = compare4.json()
    assert len(c4_data["products"]) == 4

    # Test empty IDs parameter
    compare_empty = await async_client.get("/api/products/compare?ids=")
    assert compare_empty.status_code == status.HTTP_400_BAD_REQUEST

    # Test non-existent ID
    compare_404 = await async_client.get("/api/products/compare?ids=non_existent_product_id")
    assert compare_404.status_code == status.HTTP_404_NOT_FOUND

