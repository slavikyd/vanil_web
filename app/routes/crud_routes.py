from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.infrastructure.redis.cart_repo import RedisCartRepo
from app.infrastructure.uow import AsyncpgUnitOfWork
from app.routes.deps import get_cart_repo, get_uow
from app.routes.session_utils import get_or_create_session_id
from app.services.cart_service import CartService
from app.services.order_service import EmptyCartError, InvalidOrderDateError, OrderService
from app.services.public_service import PublicService
from app.settings.config import templates

router = APIRouter(tags=["crud"])


@router.post("/add-to-cart")
async def add_to_cart(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
    cart_repo: RedisCartRepo = Depends(get_cart_repo),
    itemid: str = Form(...),
    quantity: int = Form(...),
    tg_id: str | None = Form(None),
):
    session = request.session
    session_id = get_or_create_session_id(session)

    if tg_id:
        session["tg_id"] = tg_id

    await CartService.set_item(
        cart_repo=cart_repo,
        session_id=session_id,
        item_id=itemid,
        quantity=quantity,
    )
    cart = await CartService.get_cart(cart_repo=cart_repo, session_id=session_id)
    items_data = await PublicService.list_active_items(uow=uow)

    return JSONResponse({"cart": cart, "items_data": items_data})


@router.post("/remove-from-cart")
async def remove_from_cart(
    request: Request,
    cart_repo: RedisCartRepo = Depends(get_cart_repo),
    item_id: str = Form(...),
):
    session_id = get_or_create_session_id(request.session)
    await CartService.set_item(
        cart_repo=cart_repo,
        session_id=session_id,
        item_id=item_id,
        quantity=0,
    )
    return RedirectResponse("/", status_code=302)


@router.post("/place_order")
async def place_order(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
    cart_repo: RedisCartRepo = Depends(get_cart_repo),
    order_for: str = Form(...),
    tg_id: str | None = Form(None),
):
    session = request.session

    cashier_id = session.get("cashier_id")
    if not cashier_id:
        return RedirectResponse("/", status_code=302)

    session_id = session.get("session_id")
    if not session_id:
        return HTMLResponse("Invalid session", status_code=400)

    if tg_id:
        session["tg_id"] = tg_id

    shop_id = session.get("tg_id")

    cart = await CartService.get_cart(cart_repo=cart_repo, session_id=session_id)

    try:
        await OrderService.create_order(
            uow=uow,
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

    await CartService.clear_cart(cart_repo=cart_repo, session_id=session_id)
    return RedirectResponse("/", status_code=302)


@router.get("/orders", response_class=HTMLResponse)
async def orders_view(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
):
    cashier_id = request.session.get("cashier_id")
    if not cashier_id:
        return RedirectResponse("/", status_code=302)

    assert uow.orders is not None
    orders = await uow.orders.list_orders_for_view()

    return templates.TemplateResponse("orders.html", {"request": request, "orders": orders})
