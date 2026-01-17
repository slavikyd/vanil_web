"""
Публичные данные (товары для главной/корзины)
"""

from typing import Dict, List

from asyncpg import Connection


async def list_active_items(db: Connection) -> List[Dict]:
    """
    Активные товары (используется в index + add-to-cart)
    """
    rows = await db.fetch(
        """
        SELECT id, name, price 
        FROM items 
        WHERE active = TRUE 
        ORDER BY name ASC
    """
    )
    return [
        {"id": str(r['id']), "name": r['name'], "price": float(r['price'])}
        for r in rows
    ]
