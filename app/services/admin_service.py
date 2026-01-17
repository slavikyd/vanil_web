import io
import logging
import uuid
from collections import defaultdict
from datetime import date, datetime
from io import BytesIO
from uuid import UUID

import openpyxl
from openpyxl import Workbook


class AdminService:

    @staticmethod
    async def create_item(db, name: str, price: float, ttl: int):
        async with db.acquire() as conn:
            await conn.execute(
                'INSERT INTO items (name, price, ttl, active) VALUES ($1, $2, $3, TRUE)',
                name,
                price,
                ttl,
            )

    @staticmethod
    async def delete_item(db, item_id: uuid.UUID):
        async with db.acquire() as conn:
            await conn.execute(
                'DELETE FROM items WHERE id = $1',
                item_id,
            )

    @staticmethod
    async def list_items(db):
        async with db.acquire() as conn:
            return await conn.fetch('SELECT id, name, active FROM items ORDER BY name')

    @staticmethod
    async def toggle_items(db, active_map: dict):
        async with db.acquire() as conn:
            for item_id, is_active in active_map.items():
                await conn.execute(
                    'UPDATE items SET active = $1 WHERE id = $2',
                    is_active,
                    item_id,
                )

    @staticmethod
    async def get_orders(db, order_for: str | None, address: str | None):
        where = []
        args = []
        idx = 1

        if order_for:
            try:
                order_date = datetime.strptime(order_for, '%Y-%m-%d').date()
                where.append(f'o.order_for = ${idx}')
                args.append(order_date)
                idx += 1
            except ValueError:
                logging.warning(f'Invalid date: {order_for}')

        if address:
            where.append(f'o.address ILIKE ${idx}')
            args.append(f'%{address}%')
            idx += 1

        where_sql = f"WHERE {' AND '.join(where)}" if where else ''

        async with db.acquire() as conn:
            rows = await conn.fetch(
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
                {where_sql}
                ORDER BY o.order_for ASC, o.created ASC
                """,
                *args,
            )

        grouped = {}
        for r in rows:
            d = r['order_for']
            oid = str(r['order_id'])
            grouped.setdefault(d, {}).setdefault(
                oid,
                {
                    'id': oid,
                    'created': r['created'],
                    'address': r['address'],
                    'cashier_name': r['cashier_name'],
                    'items': [],
                },
            )['items'].append({'name': r['item_name'], 'quantity': r['quantity']})

        return grouped

    @staticmethod
    async def delete_order(db, order_id: uuid.UUID):
        async with db.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    'DELETE FROM orders_items WHERE order_id = $1',
                    order_id,
                )
                result = await conn.execute(
                    'DELETE FROM orders WHERE id = $1',
                    order_id,
                )
        return 'DELETE' in result

    @staticmethod
    async def export_orders(db, address: str | None):
        async with db.acquire() as conn:
            query = """
                SELECT o.id, o.created, o.address, c.full_name AS cashier_name
                FROM orders o
                JOIN cashiers c ON o.cashier_id = c.id
            """
            args = []
            if address:
                query += ' WHERE o.address ILIKE $1'
                args.append(f'%{address}%')
            query += ' ORDER BY o.created DESC'

            orders = await conn.fetch(query, *args)

            wb = Workbook()
            wb.remove(wb.active)
            sheets = {}

            for o in orders:
                addr = o['address'] or 'Unknown'
                name = addr[:31]
                ws = sheets.setdefault(
                    name,
                    wb.create_sheet(title=name),
                )

                if ws.max_row == 1:
                    ws.append(
                        [
                            'Order ID',
                            'Created',
                            'Address',
                            'Cashier',
                            'Item',
                            'Qty',
                            'Price',
                        ]
                    )

                items = await conn.fetch(
                    """
                    SELECT oi.quantity, i.name, i.price
                    FROM orders_items oi
                    JOIN items i ON i.id = oi.item_id
                    WHERE oi.order_id = $1
                    """,
                    o['id'],
                )

                for it in items:
                    ws.append(
                        [
                            str(o['id']),
                            o['created'].strftime('%Y-%m-%d %H:%M:%S'),
                            o['address'],
                            o['cashier_name'],
                            it['name'],
                            it['quantity'],
                            float(it['price']),
                        ]
                    )

        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)
        return stream

    @staticmethod
    async def export_by_address(db, order_for: date):
        async with db.acquire() as conn:
            rows = await conn.fetch(
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

        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        grouped = defaultdict(list)
        for r in rows:
            grouped[r['address']].append((r['name'], r['quantity']))

        for addr, items in grouped.items():
            ws = wb.create_sheet(title=addr[:31])
            ws.append(['Item', 'Quantity'])
            for n, q in items:
                ws.append([n, q])

        output = BytesIO()
        wb.save(output)
        output.seek(0)
        return output


def parse_toggle_form(self, form):
    """Парсит active_ чекбоксы"""
    return [UUID(k[7:]) for k in form.keys() if k.startswith("active_")]


async def toggle_items_form(self, db, form):
    """Toggle из формы"""
    active_ids = self.parse_toggle_form(form)
    await self.toggle_items(db, active_ids, active=True)
