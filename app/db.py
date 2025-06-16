import os

import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def connect_db():
    return await asyncpg.create_pool(
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        database=os.getenv("DB_NAME"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 5432)),
    )


async def load_all_orders_with_items(conn: asyncpg.Connection) -> list:
    orders_raw = await conn.fetch("""
        SELECT 
            o.id AS order_id,
            o.created,
            o.cashier_id,
            o.address,
            o.shop_id,
            c.name AS cashier_name
        FROM orders o
        LEFT JOIN cashiers c ON o.cashier_id = c.id
        ORDER BY o.created DESC
    """)

    result = []
    for order in orders_raw:
        items = await conn.fetch("""
            SELECT 
                i.name, oi.quantity, i.price
            FROM order_items oi
            JOIN items i ON i.id = oi.item_id
            WHERE oi.order_id = $1
        """, order["order_id"])

        result.append({
            "id": order["order_id"],
            "created": order["created"],
            "cashier": order["cashier_name"] or f"ID {order['cashier_id']}",
            "address": order["address"],
            "shop": order["shop_id"],
            "items": [dict(item) for item in items]
        })
    return result