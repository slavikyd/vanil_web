from asyncpg import Connection


class ShopsRepo:
    def __init__(self, conn: Connection):
        self._conn = conn

    async def get_address(self, *, shop_id: str) -> str | None:
        row = await self._conn.fetchrow(
            'SELECT address FROM shops WHERE id = $1', shop_id
        )
        return row['address'] if row else None
