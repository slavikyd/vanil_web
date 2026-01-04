"""CRUD routes for orders and cart management.

Includes endpoints for:
- Adding items to cart/order
- Placing orders
- Viewing orders
"""

import logging
import uuid
from datetime import datetime

from app.settings.config import templates
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

router = APIRouter(tags=["orders"])


class AddToOrderRequest(BaseModel):
    item_id: str
    quantity: int
    tg_id: str = None


def get_session_cart(request: Request, router: APIRouter) -> dict:
    """Get or create cart for the current session."""
    session_id = request.session.get("session_id")
    
    if not hasattr(router, "carts"):
        router.carts = {}
    
    if not session_id or session_id not in router.carts:
        session_id = str(uuid.uuid4())
        router.carts[session_id] = {}
        request.session["session_id"] = session_id
    
    return router.carts[session_id]


@router.post("/add-to-order")
async def add_to_order(request: Request, order_data: AddToOrderRequest):
    """Add item to cart or update quantity."""
    cashier_id = request.session.get("cashier_id")
    if not cashier_id:
        return JSONResponse({"error": "Unauthorized: No cashier logged in"}, status_code=401)

    # Get or create cart
    if not hasattr(router, "carts"):
        router.carts = {}
    
    session_id = request.session.get("session_id")
    if not session_id or session_id not in router.carts:
        session_id = str(uuid.uuid4())
        router.carts[session_id] = {}
        request.session["session_id"] = session_id

    cart = router.carts[session_id]

    item_id = order_data.item_id
    quantity = order_data.quantity

    if quantity > 0:
        cart[item_id] = quantity
    else:
        cart.pop(item_id, None)

    async with request.app.state.db.acquire() as conn:
        items_from_db = await conn.fetch("SELECT id, name, price FROM items ORDER BY name ASC")

    items_list_for_json = []
    for item in items_from_db:
        items_list_for_json.append({
            "id": str(item["id"]),
            "name": item["name"],
            "price": float(item["price"])
        })

    serializable_cart = {str(k): v for k, v in cart.items()}

    return JSONResponse({"cart": serializable_cart, "items_data": items_list_for_json})


@router.post("/place_order")
async def place_order(request: Request, tg_id: str = Form(...), order_for: str = Form(...)):
    """Place an order from the current cart."""
    cashier_id = request.session.get("cashier_id")
    if not cashier_id:
        return RedirectResponse("/", status_code=302)

    db = request.app.state.db

    # Verify shop exists
    shop = await db.fetchrow("SELECT id FROM shops WHERE id = $1", tg_id)
    if not shop:
        logging.error(f"Shop with tg_id {tg_id} not found when placing order.")
        return HTMLResponse("Shop not registered", status_code=400)

    # Get shop address
    async with db.acquire() as conn:
        address_records = await conn.fetch("SELECT * from shops where id = $1", tg_id)

    if not address_records:
        logging.error(f"Shop address not found for tg_id {tg_id}")
        return HTMLResponse("Shop address not found", status_code=400)

    # Verify cashier exists
    cashier = await db.fetchrow("SELECT id FROM cashiers WHERE id = $1", cashier_id)
    if not cashier:
        logging.error(f"Cashier with ID {cashier_id} not found when placing order.")
        return HTMLResponse("Cashier not registered", status_code=400)

    order_id = uuid.uuid4()

    # Convert order_for from string to date object
    try:
        order_for_date = datetime.strptime(order_for, "%Y-%m-%d").date()
    except ValueError as e:
        logging.error(f"Invalid date format for order_for: {order_for}")
        return HTMLResponse(f"Invalid date format for order_for: {order_for}", status_code=400)

    try:
        async with db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO orders (id, cashier_id, shop_id, address, order_for)
                VALUES ($1, $2, $3, $4, $5)
                """,
                order_id, cashier_id, tg_id, address_records[0]['address'], order_for_date
            )

            session_id = request.session.get("session_id")
            if not hasattr(router, "carts"):
                router.carts = {}
            
            cart = router.carts.get(session_id, {})

            if not cart:
                logging.warning(f"Attempted to place an empty order for cashier {cashier_id}, session {session_id}")
                return HTMLResponse("Your cart is empty. Nothing to order.", status_code=400)

            for item_id, qty in cart.items():
                if qty > 0:
                    await conn.execute(
                        "INSERT INTO orders_items (order_id, item_id, quantity) VALUES ($1, $2, $3)",
                        order_id, uuid.UUID(item_id), qty
                    )

        if session_id in router.carts:
            del router.carts[session_id]

        return RedirectResponse("/", status_code=302)
    except Exception as e:
        logging.error(f"Error placing order: {e}", exc_info=True)
        return HTMLResponse(f"An error occurred while placing your order: {e}", status_code=500)


@router.get("/orders", response_class=HTMLResponse)
async def orders_view(request: Request):
    """View all orders placed by any cashier."""
    cashier_id = request.session.get("cashier_id")
    if not cashier_id:
        return RedirectResponse("/", status_code=302)

    async with request.app.state.db.acquire() as conn:
        orders = await conn.fetch("""
            SELECT o.id, o.created, o.address, c.id as cashier_id, s.id as shop_id, c.is_admin as is_admin, c.full_name AS cashier_name
            FROM orders o
            JOIN cashiers c ON o.cashier_id = c.id
            JOIN shops s on o.shop_id = s.id
            ORDER BY o.created DESC;
        """)

        orders_data = []
        for order in orders:
            items = await conn.fetch("""
                SELECT oi.quantity, i.name, i.price
                FROM orders_items oi
                JOIN items i ON i.id = oi.item_id
                WHERE oi.order_id = $1
            """, order["id"])

            serializable_items = []
            for item in items:
                serializable_items.append({
                    "quantity": item["quantity"],
                    "name": item["name"],
                    "price": float(item["price"]),
                })

            orders_data.append({
                "id": str(order["id"]),
                "created": order["created"],
                "address": order["address"],
                "cashier_name": order["cashier_name"],
                "items": serializable_items,
                "cashier_id": str(order['cashier_id']),
                "shop_id": str(order['shop_id']),
            })

    return templates.TemplateResponse("orders.html", {"request": request, "orders": orders_data})
