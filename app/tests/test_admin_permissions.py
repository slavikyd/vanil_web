from app.tests.fixtures.constants import ADMIN_ID


async def test_admin_access_allowed(client, mock_db_pool):
    pool, conn = mock_db_pool

    # First call: login lookup
    # Second call: maybe permission check
    conn.fetchrow.side_effect = [
        {
            "id": ADMIN_ID,
            "name": "Admin",
            "is_admin": True,
        },
        {
            "id": ADMIN_ID,
            "name": "Admin",
            "is_admin": True,
        },
    ]

    await client.post("/login", data={"cashier_id": ADMIN_ID})

    response = await client.get("/admin/items")

    assert response.status_code == 200
