"""
Index service: сбор данных для главной страницы и JSON API.

Идея: вынести из роутов:
- получение/создание session_id
- чтение корзины
- выборку активных товаров
- вычисление is_admin
"""

from typing import Any, Dict, List

from fastapi import Request

from app.services.cart_service import get_cart, get_or_create_session_id
from app.services.public_service import list_active_items


async def get_index_context(request: Request) -> Dict[str, Any]:
    """
    Контекст для TemplateResponse("index.html", ...)

    Возвращает:
    - items: List[{id, name, price}]
    - cart: Dict[item_id -> qty]
    - cashier_id: str
    - is_admin: bool
    """
    cashier_id = request.session.get("cashier_id")
    if not cashier_id:
        return {
            "items": [],
            "cart": {},
            "cashier_id": None,
            "is_admin": False,
        }

    session_id = get_or_create_session_id(request)
    cart = await get_cart(session_id)

    async with request.app.state.db.acquire() as conn:
        items: List[Dict[str, Any]] = await list_active_items(conn)
        row = await conn.fetchrow(
            "SELECT is_admin FROM cashiers WHERE id = $1",
            cashier_id,
        )
        is_admin = bool(row and row["is_admin"])

    return {
        "items": items,
        "cart": cart,
        "cashier_id": cashier_id,
        "is_admin": is_admin,
    }


async def get_api_data(request: Request) -> Dict[str, Any]:
    """
    Данные для /api/data (без корзины, как было в исходном extra_routes.py).

    Возвращает:
    - items: List[{id, name, price}]
    - is_admin: bool
    """
    cashier_id = request.session.get("cashier_id")
    if not cashier_id:
        return {"error": "Not logged in"}

    async with request.app.state.db.acquire() as conn:
        items: List[Dict[str, Any]] = await list_active_items(conn)
        row = await conn.fetchrow(
            "SELECT is_admin FROM cashiers WHERE id = $1",
            cashier_id,
        )
        is_admin = bool(row and row["is_admin"])

    return {"items": items, "is_admin": is_admin}
