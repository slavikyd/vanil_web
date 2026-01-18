import uuid
from asyncpg import Connection


class ItemsRepo:
    def __init__(self, conn: Connection):
        self._conn = conn

    async def list_active(self) -> list[dict]:
        rows = await self._conn.fetch(
            """
            SELECT id, name, price
            FROM items
            WHERE active = TRUE
            ORDER BY name ASC
            """
        )
        return [{"id": str(r["id"]), "name": r["name"], "price": float(r["price"])} for r in rows]

    async def list_for_admin(self) -> list[dict]:
        rows = await self._conn.fetch(
            """
            SELECT id, name, active
            FROM items
            ORDER BY name
            """
        )
        return [{"id": str(r["id"]), "name": r["name"], "active": bool(r["active"])} for r in rows]

    async def create(self, *, name: str, price: float, ttl: int) -> None:
        await self._conn.execute(
            """
            INSERT INTO items (name, price, ttl, active)
            VALUES ($1, $2, $3, TRUE)
            """,
            name,
            price,
            ttl,
        )

    async def delete(self, *, item_id: uuid.UUID) -> None:
        await self._conn.execute("DELETE FROM items WHERE id = $1", item_id)

    async def set_active(self, *, item_id: uuid.UUID, active: bool) -> None:
        await self._conn.execute("UPDATE items SET active = $1 WHERE id = $2", active, item_id)
