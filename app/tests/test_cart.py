"""
Test cart operations with mocked DB and Redis.
"""

from app.tests.fixtures.constants import ADMIN_ID, ITEM_ID


async def test_add_item_to_cart(client, mock_db_pool, mock_redis):
    pool, conn = mock_db_pool

    # login: SELECT id FROM cashiers WHERE id=$1
    conn.fetchrow.return_value = {"id": ADMIN_ID}

    # /add-to-cart делает SELECT items...
    conn.fetch.return_value = [{"id": ITEM_ID, "name": "Test Item", "price": 10.0}]

    # get_cart() после set_item()
    mock_redis.hgetall.return_value = {str(ITEM_ID): "2"}

    resp_login = await client.post(
        "/login", data={"cashier_id": ADMIN_ID}, follow_redirects=False
    )
    assert resp_login.status_code == 302

    response = await client.post(
        "/add-to-cart",
        data={"itemid": str(ITEM_ID), "quantity": 2},
        follow_redirects=False,
    )

    assert response.status_code == 200
    data = response.json()

    assert data["cart"][str(ITEM_ID)] == 2
    assert any(i["id"] == str(ITEM_ID) for i in data["items_data"])


async def test_add_item_to_cart_no_session(client, mock_db_pool, mock_redis):
    # Даже без логина корзина должна работать (session_id создаётся автоматически)
    pool, conn = mock_db_pool
    conn.fetch.return_value = []
    mock_redis.hgetall.return_value = {str(ITEM_ID): "1"}

    response = await client.post(
        "/add-to-cart",
        data={"itemid": str(ITEM_ID), "quantity": 1},
        follow_redirects=False,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["cart"][str(ITEM_ID)] == 1


async def test_remove_from_cart(client, mock_redis):
    response = await client.post(
        "/remove-from-cart",
        data={"itemid": str(ITEM_ID)},  # было item_id
        follow_redirects=False,
    )
    assert response.status_code == 302


async def test_place_order_empty_cart(client, mock_db_pool, mock_redis):
    pool, conn = mock_db_pool
    conn.fetchrow.return_value = {"id": ADMIN_ID}  # login ok
    mock_redis.hgetall.return_value = {}  # empty cart

    await client.post("/login", data={"cashier_id": ADMIN_ID}, follow_redirects=False)

    response = await client.post(
        "/place_order",
        data={"order_for": "2026-01-17", "tg_id": "shop-test"},
        follow_redirects=False,
    )

    assert response.status_code == 400
