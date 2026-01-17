from app.tests.fixtures.constants import ADMIN_ID, ITEM_ID, SHOP_ID


async def test_place_order_success(client, mock_db_pool, mock_redis):
    pool, conn = mock_db_pool

    # 1) login lookup: SELECT id FROM cashiers ...
    # 2) create_order shop lookup: SELECT address FROM shops ...
    conn.fetchrow.side_effect = [
        {"id": ADMIN_ID},
        {"address": "Test Address"},
    ]

    mock_redis.hgetall.return_value = {str(ITEM_ID): "2"}
    mock_redis.delete.return_value = None

    resp_login = await client.post("/login", data={"cashier_id": ADMIN_ID}, follow_redirects=False)
    assert resp_login.status_code == 302

    response = await client.post(
        "/place_order",
        data={"tg_id": SHOP_ID, "order_for": "2030-01-01"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert mock_redis.delete.await_count >= 1
