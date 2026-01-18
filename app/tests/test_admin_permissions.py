import app.http_codes as code
from app.tests.fixtures.constants import ADMIN_ID


async def test_admin_access_allowed(client, mock_db_pool):
    pool, conn = mock_db_pool

    async def fetchrow_side_effect(query: str, *args, **kwargs):
        q = (query or '').lower()
        if 'from cashiers' in q and 'select id' in q:
            return {'id': ADMIN_ID}
        if 'from cashiers' in q and ('is_admin' in q or 'isadmin' in q):
            return {'is_admin': True, 'isadmin': True}
        return None

    conn.fetchrow.side_effect = fetchrow_side_effect
    conn.fetch.return_value = []

    resp_login = await client.post(
        '/login',
        data={'cashierid': ADMIN_ID, 'cashier_id': ADMIN_ID},
        follow_redirects=False,
    )
    assert resp_login.status_code != code.UNPROCESSABLE_ENTITY, resp_login.text
    assert resp_login.status_code == code.FOUND

    response = await client.get('/admin/items', follow_redirects=False)
    assert response.status_code in (
        code.OK,
        code.FOUND,
    ), response.text
