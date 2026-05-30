import logging
import uuid
from datetime import date
from typing import Literal

from asyncpg import Connection


class OrdersRepo:
    def __init__(self, conn: Connection):
        self._conn = conn

    # TODO: maybe I don't need this here...
    def group_orders_by_day(self, rows: list[dict]) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for r in rows:
            oid = r['order_id']
            day_key = r['order_for'].isoformat()
            day_bucket = grouped.setdefault(day_key, [])
            order = next((o for o in day_bucket if o['id'] == oid), None)
            if order is None:
                order = {
                    'id': oid,
                    'created': r['created'],
                    'address': r['address'],
                    'items': [],
                }
                day_bucket.append(order)
            order['items'].append({'name': r['item_name'], 'quantity': r['quantity']})
        return grouped
    

    async def create_order(
        self,
        *,
        order_id: uuid.UUID,
        cashier_id: str,
        shop_id: str,
        address: str,
        order_for: date,
        comment: str | None,
        shipment: int,
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO orders (id, cashier_id, shop_id, address, order_for, comment, shipment)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            order_id,
            cashier_id,
            shop_id,
            address,
            order_for,
            comment,
            shipment,
        )

    async def add_items(
        self,
        order_id: uuid.UUID,
        cart: dict[str, int],
        comments: dict[str, str],
        order_types: dict[str, str],
    ) -> None:

        item_ids = [uuid.UUID(item_id) for item_id in cart]
        quantities = list(cart.values())
        notes = [(comments.get(item_id) or '').strip() or None for item_id in cart]
        types = [order_types.get(item_id) or 'Обычный' for item_id in cart]
        logging.getLogger(__name__).warning(f'DEBUG types: {types}')
        logging.getLogger(__name__).warning(f'DEBUG notes: {notes}')
        logging.getLogger(__name__).warning(f'DEBUG comments: {comments}')
        logging.getLogger(__name__).warning(f'DEBUG cart keys: {list(cart.keys())}')

        await self._conn.execute(
            """
            INSERT INTO orders_items (order_id, item_id, quantity, comment, order_type)
            SELECT $1, unnest($2::uuid[]), unnest($3::int[]), unnest($4::text[]), unnest($5::text[])
            """,
            order_id,
            item_ids,
            quantities,
            notes,
            types,
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
                'id': r['id'],
                'created': r['created'],
                'address': r['address'],
                'cashier_name': r['cashier_name'],
            }
            for r in rows
        ]

    async def delete_order(self, *, order_id: uuid.UUID) -> bool:
        async with self._conn.transaction():
            await self._conn.execute(
                'DELETE FROM orders_items WHERE order_id = $1', order_id
            )
            res = await self._conn.execute('DELETE FROM orders WHERE id = $1', order_id)
        return 'DELETE' in res

    async def admin_rows(
        self, *, order_for: date | None, address: str | None
    ) -> list[dict]:
        where = []
        args: list[object] = []
        idx = 1

        if order_for is not None:
            where.append(f'o.order_for = ${idx}')
            args.append(order_for)
            idx += 1

        if address:
            where.append(f'o.address ILIKE ${idx}')
            args.append(f'%{address}%')
            idx += 1

        wheresql = f'WHERE {" AND ".join(where)}' if where else ''

        rows = await self._conn.fetch(
            f"""
            SELECT
            o.id AS order_id,
            o.order_for,
            o.created,
            o.address,
            c.full_name AS cashier_name,
            oi.quantity,
            oi.order_type,
            i.name AS item_name,
            sg.name AS group_name
            FROM orders o
            JOIN cashiers c ON o.cashier_id = c.id
            JOIN orders_items oi ON oi.order_id = o.id
            JOIN items i ON oi.item_id = i.id
            LEFT JOIN shops s ON o.shop_id = s.id
            LEFT JOIN shops_groups sg ON s.shop_group = sg.id
            {wheresql}
            ORDER BY o.order_for DESC, o.created DESC
            """,
            *args,
        )

        return [
            {
                'order_id': r['order_id'],
                'order_for': r['order_for'],
                'created': r['created'],
                'address': r['address'],
                'cashier_name': r['cashier_name'],
                'item_name': r['item_name'],
                'quantity': r['quantity'],
                'order_type': r['order_type'],
                'group_name': r['group_name'],  
            }
            for r in rows
        ]

    async def cashier_rows(self, *, cashier_id: str, date_filter: Literal['today', 'past', 'future']) -> list[dict]:

        today = date.today()

        conditions = {
            'today': 'o.order_for = $2',
            'past': 'o.order_for < $2',
            'future': 'o.order_for > $2',
        }

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
                WHERE o.cashier_id = $1 AND {conditions[date_filter]}
                ORDER BY o.order_for DESC, o.created DESC
            """,
            cashier_id,
            today,
        )
        return [
            {
                'order_id': r['order_id'],
                'order_for': r['order_for'],
                'created': r['created'],
                'address': r['address'],
                'item_name': r['item_name'],
                'quantity': int(r['quantity']),
                'cashier_name': r['cashier_name'],
            }
            for r in rows
        ]

    async def export_orders_list(self, *, address: str | None) -> list[dict]:
        args: list[object] = []
        where = ''
        if address:
            where = 'WHERE o.address ILIKE $1'
            args.append(f'%{address}%')

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
                'id': r['id'],
                'created': r['created'],
                'address': r['address'],
                'cashier_name': r['cashier_name'],
            }
            for r in rows
        ]

    async def export_order_items(self, *, order_id: uuid.UUID) -> list[dict]:
        rows = await self._conn.fetch(
            """
            SELECT oi.quantity, i.name
            FROM orders_items oi
            JOIN items i ON i.id = oi.item_id
            WHERE oi.order_id = $1
            """,
            order_id,
        )
        return [
            {'name': r['name'], 'quantity': r['quantity']}
            for r in rows
        ]

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
        return [
            {'address': r['address'], 'name': r['name'], 'quantity': r['quantity']}
            for r in rows
        ]

