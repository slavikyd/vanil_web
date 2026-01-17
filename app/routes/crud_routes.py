"""
CRUD routes for orders and cart management.
"""

import logging
import uuid

from app.redis import redis
from app.services.cart_service import clear_cart, get_cart, set_item
from app.services.order_service import (EmptyCartError, InvalidOrderDateError,
                                        create_order)
from app.settings.config import templates
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

router = APIRouter(tags=["crud"])


@router.post("/add-to-cart")
async def add_to_cart(
    request: Request,
    item_id: str = Form(...),
    quantity: int = Form(...),
):
    session_id = request.session.get("session_id")
    if not session_id:
        return RedirectResponse("/", status_code=302)

    await set_item(session_id, item_id, quantity)

    return RedirectResponse("/", status_code=302)


@router.post("/remove-from-cart")
async def remove_from_cart(
    request: Request,
    item_id: str = Form(...),
):
    session_id = request.session.get("session_id")
    if not session_id:
        return RedirectResponse("/", status_code=302)

    await set_item(session_id, item_id, 0)

    return RedirectResponse("/", status_code=302)


@router.post("/place_order")
async def place_order(
    request: Request,
    order_for: str = Form(...),
):
    session = request.session

    cashier_id = session.get("cashier_id")
    shop_id = session.get("tg_id")
    session_id = session.get("session_id")

    if not cashier_id:
        return RedirectResponse("/", status_code=302)

    if not shop_id or not session_id:
        return HTMLResponse("Invalid session", status_code=400)


    cart = await get_cart(session_id)

    try:
        await create_order(
            db=request.app.state.db,
            cashier_id=cashier_id,
            shop_id=shop_id,
            cart=cart,
            order_for=order_for,
        )
    except EmptyCartError:
        return HTMLResponse("Cart is empty", status_code=400)
    except InvalidOrderDateError:
        return HTMLResponse("Invalid order date", status_code=400)
    except Exception as e:
        return HTMLResponse(f"Failed to create order: {e}", status_code=500)

    await clear_cart(session_id)

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
