from app.tests.fixtures.constants import ADMIN_ID


async def test_admin_access_allowed(client, mock_db_pool):
    pool, conn = mock_db_pool

    conn.fetchrow.side_effect = [
        {"id": ADMIN_ID},
        {"is_admin": True},
    ]

    conn.fetch.return_value = []

    await client.post("/login", data={"cashier_id": ADMIN_ID}, follow_redirects=False)
    response = await client.get("/admin/items", follow_redirects=False)

    assert response.status_code == 200
