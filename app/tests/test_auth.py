from app.tests.fixtures.constants import ADMIN_ID


async def test_login_success(client, mock_db_pool):
    pool, conn = mock_db_pool

    # login -> AuthService.cashier_exists -> repo -> SELECT ... FROM cashiers ...
    async def fetchrow_side_effect(query: str, *args, **kwargs):
        q = (query or "").lower()
        if "from cashiers" in q:
            return {"id": ADMIN_ID}
        return None

    conn.fetchrow.side_effect = fetchrow_side_effect

    # ВАЖНО: отправляем оба варианта имени поля
    response = await client.post(
        "/login",
        data={"cashierid": ADMIN_ID, "cashier_id": ADMIN_ID},
        follow_redirects=False,
    )

    assert response.status_code != 422, response.text
    assert response.status_code == 302
