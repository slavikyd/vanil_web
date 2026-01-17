from app.tests.fixtures.constants import ADMIN_ID


async def test_login_success(client, mock_db_pool):
    pool, conn = mock_db_pool

    # When login queries cashier by id, return a valid admin row
    conn.fetchrow.return_value = {
        "id": ADMIN_ID,
        "name": "Admin",
        "is_admin": True,
    }

    response = await client.post(
        "/login",
        data={"cashier_id": ADMIN_ID},
        follow_redirects=False,
    )

    assert response.status_code == 302
