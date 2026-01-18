import uuid
from datetime import date
from asyncpg import Connection


class OrdersRepo:
    def __init__(self, conn: Connection):
        self._conn = conn

    async def create_order(
        self,
        *,
        order_id: uuid.UUID,
        cashier_id: str,
        shop_id: str,
        address: str,
        order_for: date,
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO orders (id, cashier_id, shop_id, address, order_for)
            VALUES ($1, $2, $3, $4, $5)
            """,
            order_id,
            cashier_id,
            shop_id,
            address,
            order_for,
        )

    async def add_items(self, *, order_id: uuid.UUID, cart: dict[str, int]) -> None:
        for item_id, qty in cart.items():
            await self._conn.execute(
                """
                INSERT INTO orders_items (order_id, item_id, quantity)
                VALUES ($1, $2, $3)
                """,
                order_id,
                uuid.UUID(item_id),
                qty,
            )

    async def list_orders_for_view(self) -> list[dict]:
        rows = await self._conn.fetch(
            """
            SELECT o.id, o.created, o.address, c.full_name AS cashier_name
            FROM orders o
            JOIN cashiers c ON o.cashier_id = c.id
            ORDER BY o.created DESC
            """
        )
        return [
            {
                "id": str(r["id"]),
                "created": r["created"],
                "address": r["address"],
                "cashier_name": r["cashier_name"],
            }
            for r in rows
        ]

    async def delete_order(self, *, order_id: uuid.UUID) -> bool:
        async with self._conn.transaction():
            await self._conn.execute("DELETE FROM orders_items WHERE order_id = $1", order_id)
            res = await self._conn.execute("DELETE FROM orders WHERE id = $1", order_id)
        return "DELETE" in res

    async def admin_rows(self, *, order_for: date | None, address: str | None) -> list[dict]:
        where = []
        args: list[object] = []
        idx = 1

        if order_for is not None:
            where.append(f"o.order_for = ${idx}")
            args.append(order_for)
            idx += 1

        if address:
            where.append(f"o.address ILIKE ${idx}")
            args.append(f"%{address}%")
            idx += 1

        wheresql = f"WHERE {' AND '.join(where)}" if where else ""

        rows = await self._conn.fetch(
            f"""
            SELECT
              o.id AS order_id,
              o.order_for,
              o.created,
              o.address,
              c.full_name AS cashier_name,
              oi.quantity,
              i.name AS item_name
            FROM orders o
            JOIN cashiers c ON o.cashier_id = c.id
            JOIN orders_items oi ON oi.order_id = o.id
            JOIN items i ON oi.item_id = i.id
            {wheresql}
            ORDER BY o.order_for ASC, o.created ASC
            """,
            *args,
        )

        return [
            {
                "order_id": str(r["order_id"]),
                "order_for": r["order_for"],
                "created": r["created"],
                "address": r["address"],
                "cashier_name": r["cashier_name"],
                "item_name": r["item_name"],
                "quantity": r["quantity"],
            }
            for r in rows
        ]

    async def export_orders_list(self, *, address: str | None) -> list[dict]:
        args: list[object] = []
        where = ""
        if address:
            where = "WHERE o.address ILIKE $1"
            args.append(f"%{address}%")

        rows = await self._conn.fetch(
            f"""
            SELECT o.id, o.created, o.address, c.full_name AS cashier_name
            FROM orders o
            JOIN cashiers c ON o.cashier_id = c.id
            {where}
            ORDER BY o.created DESC
            """,
            *args,
        )

        return [
            {
                "id": str(r["id"]),
                "created": r["created"],
                "address": r["address"],
                "cashier_name": r["cashier_name"],
            }
            for r in rows
        ]

    async def export_order_items(self, *, order_id: uuid.UUID) -> list[dict]:
        rows = await self._conn.fetch(
            """
            SELECT oi.quantity, i.name, i.price
            FROM orders_items oi
            JOIN items i ON i.id = oi.item_id
            WHERE oi.order_id = $1
            """,
            order_id,
        )
        return [{"name": r["name"], "quantity": r["quantity"], "price": float(r["price"])} for r in rows]

    async def export_by_address_rows(self, *, order_for: date) -> list[dict]:
        rows = await self._conn.fetch(
            """
            SELECT o.address, i.name, oi.quantity
            FROM orders o
            JOIN orders_items oi ON o.id = oi.order_id
            JOIN items i ON oi.item_id = i.id
            WHERE o.order_for = $1
            ORDER BY o.address
            """,
            order_for,
        )
        return [{"address": r["address"], "name": r["name"], "quantity": r["quantity"]} for r in rows]