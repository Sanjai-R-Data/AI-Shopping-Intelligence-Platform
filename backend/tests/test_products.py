"""
AI-Powered Multilingual Shopping Intelligence Platform
Product Catalog & Comparison API Integration Tests.
"""

import pytest
import httpx
from fastapi import status


@pytest.mark.asyncio
async def test_list_products_all(async_client: httpx.AsyncClient):
    """Verify catalog listing returns seeded products with pagination metadata."""
    response = await async_client.get("/api/products")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "items" in data
    assert data["total"] == 18
    assert len(data["items"]) == 18
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert data["total_pages"] == 1

    # Verify first item contains lowest price and offers
    first_item = data["items"][0]
    assert "id" in first_item
    assert "name" in first_item
    assert "lowest_price" in first_item
    assert len(first_item["offers"]) >= 1


@pytest.mark.asyncio
async def test_search_products_by_name(async_client: httpx.AsyncClient):
    """Verify search filter matches product names and descriptions."""
    response = await async_client.get("/api/products?q=iPhone")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["total"] >= 1
    product_names = [p["name"] for p in data["items"]]
    assert any("iPhone 15 Pro" in name for name in product_names)


@pytest.mark.asyncio
async def test_filter_products_by_category(async_client: httpx.AsyncClient):
    """Verify category filtering isolates Electronics, Accessories, and Home Appliances."""
    # Electronics
    resp_elec = await async_client.get("/api/products?category=Electronics")
    assert resp_elec.status_code == status.HTTP_200_OK
    assert resp_elec.json()["total"] == 7
    for p in resp_elec.json()["items"]:
        assert p["category"].lower() == "electronics"

    # Accessories
    resp_acc = await async_client.get("/api/products?category=Accessories")
    assert resp_acc.status_code == status.HTTP_200_OK
    assert resp_acc.json()["total"] == 5
    for p in resp_acc.json()["items"]:
        assert p["category"].lower() == "accessories"

    # Home Appliances
    resp_home = await async_client.get("/api/products?category=Home Appliances")
    assert resp_home.status_code == status.HTTP_200_OK
    assert resp_home.json()["total"] == 6
    for p in resp_home.json()["items"]:
        assert p["category"].lower() == "home appliances"


@pytest.mark.asyncio
async def test_filter_products_by_brand(async_client: httpx.AsyncClient):
    """Verify brand filtering."""
    response = await async_client.get("/api/products?brand=Apple")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["total"] == 4
    for p in data["items"]:
        assert p["brand"].lower() == "apple"


@pytest.mark.asyncio
async def test_filter_products_by_price_range(async_client: httpx.AsyncClient):
    """Verify price range filtering returns products with offers in target range."""
    response = await async_client.get("/api/products?min_price=80&max_price=150")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["total"] >= 1
    for p in data["items"]:
        # Each returned product must have at least one offer in [80, 150]
        has_offer_in_range = any(80 <= o["price"] <= 150 for o in p["offers"])
        assert has_offer_in_range is True


@pytest.mark.asyncio
async def test_filter_products_invalid_price_range(async_client: httpx.AsyncClient):
    """Verify invalid price range (min > max) returns 400 Bad Request."""
    response = await async_client.get("/api/products?min_price=500&max_price=200")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert "min_price cannot exceed max_price" in data["detail"]


@pytest.mark.asyncio
async def test_get_product_detail_success(async_client: httpx.AsyncClient):
    """Verify full product detail endpoint returns specs, offers, and lowest price."""
    product_id = "prod_apple_iphone15_pro"
    response = await async_client.get(f"/api/products/{product_id}")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["id"] == product_id
    assert "iPhone 15 Pro" in data["name"]
    assert data["brand"] == "Apple"
    assert data["category"] == "Electronics"
    assert data["total_offers"] == 3
    assert len(data["offers"]) == 3

    # Lowest price is Amazon at 989.00
    assert data["lowest_price"] == 989.00
    assert data["lowest_price_retailer"] == "Amazon"
    assert "screen_size" in data["specifications"]
    assert "processor" in data["specifications"]


@pytest.mark.asyncio
async def test_get_product_detail_not_found(async_client: httpx.AsyncClient):
    """Verify 404 Problem Details when product ID does not exist."""
    response = await async_client.get("/api/products/non_existent_product_uuid")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    data = response.json()
    assert data["status"] == 404
    assert data["title"] == "Not Found"
    assert "non_existent_product_uuid" in data["detail"]


@pytest.mark.asyncio
async def test_compare_products_success(async_client: httpx.AsyncClient):
    """Verify product comparison matrix comparing iPhone 15 Pro and Galaxy S24 Ultra."""
    ids = "prod_apple_iphone15_pro,prod_samsung_galaxy_s24_ultra"
    response = await async_client.get(f"/api/products/compare?ids={ids}")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["compared_count"] == 2
    assert len(data["products"]) == 2

    prod_names = [p["name"] for p in data["products"]]
    assert any("iPhone 15 Pro" in n for n in prod_names)
    assert any("Galaxy S24 Ultra" in n for n in prod_names)

    # Verify comparison matrix mapping specifications
    matrix = data["comparison_matrix"]
    assert "screen_size" in matrix
    assert "processor" in matrix

    # Verify price summary
    price_summary = data["price_summary"]
    assert "cheapest_product" in price_summary
    assert price_summary["cheapest_price"] == 989.00
    assert price_summary["min_market_price"] == 989.00
    assert price_summary["max_market_price"] == 1249.99


@pytest.mark.asyncio
async def test_compare_products_invalid_ids(async_client: httpx.AsyncClient):
    """Verify 404 when comparing products with non-existent IDs."""
    response = await async_client.get("/api/products/compare?ids=fake_id_1,fake_id_2")
    assert response.status_code == status.HTTP_404_NOT_FOUND
