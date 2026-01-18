"""
Test cart operations with mocked DB and Redis.
"""

from app.tests.fixtures.constants import ADMIN_ID, ITEM_ID


async def test_add_item_to_cart(client, mock_db_pool, mock_redis):
    pool, conn = mock_db_pool

    async def fetchrow_side_effect(query: str, *args, **kwargs):
        q = (query or "").lower()
        if "from cashiers" in q:
            return {"id": ADMIN_ID}
        return None

    conn.fetchrow.side_effect = fetchrow_side_effect

    # list_active_items внутри PublicService
    conn.fetch.return_value = [{"id": ITEM_ID, "name": "Test Item", "price": 10.0}]

    # cart read-back (FakeCartRepo -> mock_redis.hgetall)
    mock_redis.hgetall.return_value = {str(ITEM_ID): "2"}

    resp_login = await client.post(
        "/login",
        data={"cashierid": ADMIN_ID, "cashier_id": ADMIN_ID},
        follow_redirects=False,
    )
    assert resp_login.status_code != 422, resp_login.text
    assert resp_login.status_code == 302

    response = await client.post(
        "/add-to-cart",
        data={
            "itemid": str(ITEM_ID),
            "item_id": str(ITEM_ID),
            "quantity": 2,
        },
        follow_redirects=False,
    )
    assert response.status_code != 422, response.text
    assert response.status_code == 200

    data = response.json()
    assert data["cart"][str(ITEM_ID)] == 2


async def test_add_item_to_cart_no_login(client, mock_db_pool, mock_redis):
    pool, conn = mock_db_pool

    conn.fetch.return_value = []
    mock_redis.hgetall.return_value = {str(ITEM_ID): "1"}

    response = await client.post(
        "/add-to-cart",
        data={
            "itemid": str(ITEM_ID),
            "item_id": str(ITEM_ID),
            "quantity": 1,
        },
        follow_redirects=False,
    )
    assert response.status_code != 422, response.text
    assert response.status_code == 200

    data = response.json()
    assert data["cart"][str(ITEM_ID)] == 1


async def test_remove_from_cart(client, mock_redis):
    response = await client.post(
        "/remove-from-cart",
        data={
            "itemid": str(ITEM_ID),
            "item_id": str(ITEM_ID),
        },
        follow_redirects=False,
    )
    assert response.status_code != 422, response.text
    assert response.status_code == 302

    # quantity=0 -> hdel должен быть вызван
    assert mock_redis.hdel.await_count >= 1


async def test_place_order_empty_cart(client, mock_db_pool, mock_redis):
    pool, conn = mock_db_pool

    async def fetchrow_side_effect(query: str, *args, **kwargs):
        q = (query or "").lower()
        if "from cashiers" in q:
            return {"id": ADMIN_ID}
        if "from shops" in q:
            return {"address": "Test Address"}
        return None

    conn.fetchrow.side_effect = fetchrow_side_effect

    mock_redis.hgetall.return_value = {}  # empty cart

    await client.post(
        "/login",
        data={"cashierid": ADMIN_ID, "cashier_id": ADMIN_ID},
        follow_redirects=False,
    )

    response = await client.post(
        "/place_order",
        data={
            # оба варианта
            "orderfor": "2030-01-01",
            "order_for": "2030-01-01",
            "tgid": "shop-test",
            "tg_id": "shop-test",
        },
        follow_redirects=False,
    )
    assert response.status_code != 422, response.text
    assert response.status_code == 400
