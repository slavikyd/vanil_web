from asyncpg import Connection


class CashiersRepo:
    def __init__(self, conn: Connection):
        self._conn = conn

    async def exists(self, *, cashier_id: str) -> bool:
        row = await self._conn.fetchrow("SELECT id FROM cashiers WHERE id = $1", cashier_id)
        return bool(row)

    async def is_admin(self, *, cashier_id: str) -> bool:
        row = await self._conn.fetchrow("SELECT is_admin FROM cashiers WHERE id = $1", cashier_id)
        return bool(row and row["is_admin"])
