"""
CRUD routes for orders and cart management.
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.redis import redis
from app.settings.config import templates

router = APIRouter(tags=["orders"])


class AddToOrderRequest(BaseModel):
    item_id: str
    quantity: int
    tg_id: str | None = None


def cart_key(session_id: str) -> str:
    return f"cart:{session_id}"


@router.post("/add-to-order")
async def add_to_order(request: Request, order_data: AddToOrderRequest):
    cashier_id = request.session.get("cashier_id")
    if not cashier_id:
        return JSONResponse({"error": "Unauthorized: No cashier logged in"}, status_code=401)

    session_id = request.session.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        request.session["session_id"] = session_id

    key = cart_key(session_id)

    if order_data.quantity > 0:
        await redis.hset(key, order_data.item_id, order_data.quantity)
        await redis.expire(key, 1800)
    else:
        await redis.hdel(key, order_data.item_id)

    async with request.app.state.db.acquire() as conn:
        items_from_db = await conn.fetch(
            "SELECT id, name, price FROM items ORDER BY name ASC"
        )

    cart = await redis.hgetall(key)

    return JSONResponse({
        "cart": cart,
        "items_data": [
            {
                "id": str(item["id"]),
                "name": item["name"],
                "price": float(item["price"]),
            }
            for item in items_from_db
        ],
    })


@router.post("/place_order")
async def place_order(
    request: Request,
    tg_id: str = Form(...),
    order_for: str = Form(...),
):
    cashier_id = request.session.get("cashier_id")
    if not cashier_id:
        return RedirectResponse("/", status_code=302)

    session_id = request.session.get("session_id")
    if not session_id:
        return HTMLResponse("Cart not found", status_code=400)

    key = cart_key(session_id)
    cart = await redis.hgetall(key)

    if not cart:
        return HTMLResponse("Your cart is empty. Nothing to order.", status_code=400)

    try:
        order_for_date = datetime.strptime(order_for, "%Y-%m-%d").date()
    except ValueError:
        return HTMLResponse("Invalid date format", status_code=400)

    db = request.app.state.db

    async with db.acquire() as conn:
        async with conn.transaction():
            shop = await conn.fetchrow(
                "SELECT id, address FROM shops WHERE id = $1", tg_id
            )
            if not shop:
                return HTMLResponse("Shop not registered", status_code=400)

            cashier = await conn.fetchrow(
                "SELECT id FROM cashiers WHERE id = $1", cashier_id
            )
            if not cashier:
                return HTMLResponse("Cashier not registered", status_code=400)

            order_id = uuid.uuid4()

            await conn.execute(
                """
                INSERT INTO orders (id, cashier_id, shop_id, address, order_for)
                VALUES ($1, $2, $3, $4, $5)
                """,
                order_id,
                cashier_id,
                tg_id,
                shop["address"],
                order_for_date,
            )

            for item_id, qty in cart.items():
                await conn.execute(
                    """
                    INSERT INTO orders_items (order_id, item_id, quantity)
                    VALUES ($1, $2, $3)
                    """,
                    order_id,
                    uuid.UUID(item_id),
                    int(qty),
                )

    await redis.delete(key)
    return RedirectResponse("/", status_code=302)


@router.get("/orders", response_class=HTMLResponse)
async def orders_view(request: Request):
    cashier_id = request.session.get("cashier_id")
    if not cashier_id:
        return RedirectResponse("/", status_code=302)

    async with request.app.state.db.acquire() as conn:
        orders = await conn.fetch("""
            SELECT o.id, o.created, o.address, c.full_name AS cashier_name
            FROM orders o
            JOIN cashiers c ON o.cashier_id = c.id
            ORDER BY o.created DESC
        """)

    return templates.TemplateResponse(
        "orders.html",
        {"request": request, "orders": orders},
    )
