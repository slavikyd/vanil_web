"""
CRUD заказов/корзины
"""
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from app.services.cart_service import get_or_create_session_id, set_item, get_cart, clear_cart
from app.services.order_service import create_order, EmptyCartError, InvalidOrderDateError
from app.services.public_service import list_active_items  # ✅ НОВЫЙ ИМПОРТ
from app.settings.config import templates

router = APIRouter(tags=["crud"])

@router.post("/add-to-cart")
async def add_to_cart(
    request: Request, 
    itemid: str = Form(...), 
    quantity: int = Form(...), 
    tgid: str | None = Form(None)
):
    session_id = get_or_create_session_id(request)
    if tgid:
        request.session["tg_id"] = tgid
    
    await set_item(session_id, itemid, quantity)
    
    cart = await get_cart(session_id)
    async with request.app.state.db.acquire() as conn:
        # ✅ БИЗНЕС ВЫНЕСЕН (1 строка вместо 4)
        items_data = await list_active_items(conn)
    
    return JSONResponse({"cart": cart, "items_data": items_data})

@router.post("/remove-from-cart")
async def remove_from_cart(request: Request, itemid: str = Form(...)):
    session_id = get_or_create_session_id(request)
    await set_item(session_id, itemid, 0)
    return RedirectResponse("/", status_code=302)

@router.post("/place_order")
async def place_order(
    request: Request, 
    order_for: str = Form(...), 
    tgid: str | None = Form(None)
):
    session = request.session
    cashier_id = session.get("cashier_id")
    session_id = session.get("session_id")
    
    if tgid:
        session["tg_id"] = tgid
    if not cashier_id:
        return RedirectResponse("/", status_code=302)
    if not session_id:
        return HTMLResponse("Invalid session", status_code=400)
    
    cart = await get_cart(session_id)
    try:
        await create_order(
            db=request.app.state.db,
            cashier_id=cashier_id,
            shop_id=session.get("tg_id"),
            cart=cart,
            order_for=order_for
        )
        await clear_cart(session_id)
        return RedirectResponse("/", status_code=302)
    except EmptyCartError:
        return HTMLResponse("Cart is empty", status_code=400)
    except InvalidOrderDateError:
        return HTMLResponse("Invalid order date", status_code=400)
    except Exception as e:
        return HTMLResponse(f"Failed to create order: {e}", status_code=500)

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
