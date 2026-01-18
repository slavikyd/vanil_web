import app.http_codes as code
from app.tests.fixtures.constants import ADMIN_ID, ITEM_ID, SHOP_ID


async def test_place_order_success(client, mock_db_pool, mock_redis):
    pool, conn = mock_db_pool

    async def fetchrow_side_effect(query: str, *args, **kwargs):
        q = (query or '').lower()
        if 'from cashiers' in q:
            return {'id': ADMIN_ID}
        if 'from shops' in q:
            return {'address': 'Test Address'}
        return None

    conn.fetchrow.side_effect = fetchrow_side_effect

    mock_redis.hgetall.return_value = {str(ITEM_ID): '2'}
    mock_redis.delete.return_value = None

    resp_login = await client.post(
        '/login',
        data={'cashierid': ADMIN_ID, 'cashier_id': ADMIN_ID},
        follow_redirects=False,
    )
    assert resp_login.status_code != code.UNPROCESSABLE_ENTITY, resp_login.text
    assert resp_login.status_code == code.FOUND

    response = await client.post(
        '/place_order',
        data={
            'orderfor': '2030-01-01',
            'order_for': '2030-01-01',
            'tgid': SHOP_ID,
            'tg_id': SHOP_ID,
        },
        follow_redirects=False,
    )
    assert response.status_code != code.UNPROCESSABLE_ENTITY, response.text
    assert response.status_code == code.FOUND

    assert mock_redis.delete.await_count >= 1
