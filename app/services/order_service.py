import uuid
from datetime import datetime

from asyncpg import Pool


class EmptyCartError(Exception):
    pass


class InvalidOrderDateError(Exception):
    pass


async def create_order(
    *,
    db: Pool,
    cashier_id: str,
    shop_id: str,
    cart: dict[str, int],
    order_for: str,
) -> uuid.UUID:
    if not cart:
        raise EmptyCartError()

    try:
        order_for_date = datetime.strptime(order_for, "%Y-%m-%d").date()
    except ValueError:
        raise InvalidOrderDateError()

    order_id = uuid.uuid4()

    async with db.acquire() as conn:
        async with conn.transaction():
            shop = await conn.fetchrow(
                "SELECT address FROM shops WHERE id = $1",
                shop_id,
            )
            if not shop:
                raise ValueError("Shop not found")

            await conn.execute(
                """
                INSERT INTO orders (id, cashier_id, shop_id, address, order_for)
                VALUES ($1, $2, $3, $4, $5)
                """,
                order_id,
                cashier_id,
                shop_id,
                shop["address"],
                order_for_date,
            )

            for item_id, qty in cart.items():
                await conn.execute(
                    """
                    INSERT INTO orders_items (order_id, item_id, quantity)
                    VALUES ($1, $2, $3)
                    """,
                    order_id,
                    uuid.UUID(item_id),
                    qty,
                )

    return order_id
