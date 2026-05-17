import uuid

from asyncpg import Connection


class ItemsRepo:
    def __init__(self, conn: Connection):
        self._conn = conn

    async def list_active(self) -> list[dict]:
        rows = await self._conn.fetch(
            """
            SELECT i.id, i.name, i.category, c.name AS category_name
            FROM items i
            LEFT JOIN categories c ON c.id = i.category
            WHERE active = TRUE
            ORDER BY c.name NULLS LAST, i.pos NULLS LAST

            """
        )
        return [
            {
                'id': str(r['id']),
                'name': r['name'],
                'category_id': str(r.get('category')) if r.get('category') else None,
                'category_name': (r.get('category_name') or 'Без категории'),
            }
            for r in rows
        ]

    # TODO: Remove as deprecated
    # async def list_for_admin(self) -> list[dict]:
    #     rows = await self._conn.fetch(
    #         """
    #         SELECT i.id, i.name, i.active, i.category, c.name AS category_name
    #         FROM items i
    #         LEFT JOIN categories c ON c.id = i.category
    #         ORDER BY c.name NULLS LAST, i.name
    #         """
    #     )
    #     return [
    #         {
    #             'id': str(r['id']),
    #             'name': r['name'],
    #             'active': bool(r['active']),
    #             'category_id': str(r.get('category')) if r.get('category') else None,
    #             'category_name': (r.get('category_name') or 'Без категории'),
    #         }
    #         for r in rows
    #     ]

    # TODO: remove as deprecated
    async def create(
        self, name: str, active: bool = True, category_id: uuid.UUID | None = None
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO items (name, active, category)
            VALUES ($1, $2, $3)
            """,
            name,
            active,
            category_id,
        )

    # TODO: remove as deprecated
    async def delete(self, *, item_id: uuid.UUID) -> None:
        await self._conn.execute('DELETE FROM items WHERE id = $1', item_id)

    # TODO: remove as deprecated
    async def update_admin_fields(
        self, *, item_id: uuid.UUID, active: bool, category_id: uuid.UUID | None
    ) -> None:
        await self._conn.execute(
            'UPDATE items SET active = $1, category = $2 WHERE id = $3',
            active,
            category_id,
            item_id,
        )

    async def list_categories(self) -> list[dict]:
        rows = await self._conn.fetch(
            """
            SELECT id, name
            FROM categories
            ORDER BY name
            """
        )
        return [{'id': str(r['id']), 'name': r['name']} for r in rows]

    # TODO: remove as deprecated
    async def create_category(self, *, name: str) -> None:
        await self._conn.execute(
            """
            INSERT INTO categories (name)
            VALUES ($1)
            ON CONFLICT (name) DO NOTHING
            """,
            name.strip(),
        )

    # TODO: remove as deprecated
    async def rename_category(self, *, category_id: uuid.UUID, name: str) -> None:
        await self._conn.execute(
            """
            UPDATE categories
            SET name = $1
            WHERE id = $2
            """,
            name.strip(),
            category_id,
        )
