from app.tests.fixtures.constants import ADMIN_ID, ITEM_ID, SHOP_ID


async def test_place_order(client, mock_redis):
    mock_redis.hgetall.return_value = {str(ITEM_ID): "2"}

    await client.post("/login", data={"cashier_id": ADMIN_ID})

    response = await client.post(
        "/place_order",
        data={
            "tg_id": SHOP_ID,
            "order_for": "2030-01-01",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
