from app.tests.fixtures.constants import ADMIN_ID, ITEM_ID, SHOP_ID, USER_ID


async def seed(conn):
    await conn.execute(
        """
        INSERT INTO cashiers (id, full_name, is_admin)
        VALUES ($1, 'Admin', TRUE),
               ($2, 'User', FALSE)
        """,
        ADMIN_ID,
        USER_ID,
    )

    await conn.execute(
        """
        INSERT INTO shops (id, address)
        VALUES ($1, 'Test Address')
        """,
        SHOP_ID,
    )

    await conn.execute(
        """
        INSERT INTO items (id, name, active)
        VALUES ($1, 'Test Item', TRUE)
        """,
        ITEM_ID,
    )
