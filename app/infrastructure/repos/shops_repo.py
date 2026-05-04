from asyncpg import Connection
import uuid

class ShopsRepo:
    def __init__(self, conn: Connection):
        self._conn = conn

    async def get_address(self, *, shop_id: str) -> str | None:
        row = await self._conn.fetchrow(
            'SELECT address FROM shops WHERE id = $1', shop_id
        )
        return row['address'] if row else None

    async def list_shops_full(self) -> list[dict]:
        rows = await self._conn_fetch(
            """
            SELECT s.id, s.address, s.shop_group, sg.name AS group_name
            FROM shops s
            LEFT JOIN shops_groups sg ON sg.id = s.shop_group
            ORDER BYs.address
        """
        )
        return [
            {
                'id': r['id'],
                'address': r['address'],
                'shop_group': r['shop_group'],
                'group_name': r['group_name'],
            }
            for r in rows
        ]
    
    async def set_shop_group(self, *, shop_id: str, group_id: str | None) -> None:
        """Pass group_id=None to remove a shop from its group."""
        await self._conn.execute(
            'UPDATE shops SET shop_group = $1 WHERE id = $2',
            group_id,
            shop_id,
        )
    
    async def list_shops(self) -> list[dict]:
        rows= await self._conn.fetch(
            'SELECT id, address FROM shops ORDER by address'
        )
        return [{'id': r['id'], 'address': r['address']} for r in rows]
    
    async def find_by_android_id(self, * android_id: str) -> str | None:
        row = await self._conn.fetchrow(
            'SELECT id FROM shops WHERE android_id = $1', android_id
        )

        return row['id'] if row else None
    
    async def link_order(self, *, shop_id: uuid.UUID, order_id: uuid.UUID) -> None:
        await self._conn.execute(
            'INSERT INTO shops_orders (shop_id, order_id) VALUES ($1, $2)',
            shop_id,
            order_id,
        )