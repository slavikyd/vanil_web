from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from datetime import date

import app.http_codes as code
from app.infrastructure.redis.cart_repo import RedisCartRepo
from app.infrastructure.uow import AsyncpgUnitOfWork
from app.routes.deps import get_cart_repo, get_uow
from app.routes.session_utils import get_or_create_session_id
from app.services.cart_service import CartService
from app.services.order_service import (EmptyCartError, InvalidOrderDateError,
                                        OrderService)
from app.services.public_service import PublicService
from app.settings.config import templates

router = APIRouter(tags=['crud'])


@router.post('/add-to-cart')
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
        session['tg_id'] = tg_id

    await CartService.set_item(
        cart_repo=cart_repo,
        session_id=session_id,
        item_id=itemid,
        quantity=quantity,
    )
    cart = await CartService.get_cart(cart_repo=cart_repo, session_id=session_id)
    items_data = await PublicService.list_active_items(uow=uow)

    return JSONResponse({'cart': cart, 'items_data': items_data})


@router.post('/remove-from-cart')
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
    return RedirectResponse('/', status_code=code.FOUND)


@router.post('/place_order')
async def place_order(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
    cart_repo: RedisCartRepo = Depends(get_cart_repo),
    order_for: str = Form(...),
    store_name: str | None = Form(None),
    tg_id: str | None = Form(None),
):
    session = request.session

    cashier_id = session.get('cashier_id')
    if not cashier_id:
        return RedirectResponse('/', status_code=code.FOUND)

    session_id = session.get('session_id')
    if not session_id:
        return HTMLResponse('Invalid session', status_code=code.BAD_REQUEST)

    # Temporarily decouple order creation from Telegram shop id.
    shop_id = None

    cart = await CartService.get_cart(cart_repo=cart_repo, session_id=session_id)

    try:
        await OrderService.create_order(
            uow=uow,
            cashier_id=cashier_id,
            shop_id=shop_id,
            cart=cart,
            order_for=order_for,
            store_name=store_name,
        )
    except EmptyCartError:
        return HTMLResponse('Cart is empty', status_code=code.BAD_REQUEST)
    except InvalidOrderDateError:
        return HTMLResponse('Invalid order date', status_code=code.BAD_REQUEST)
    except Exception as e:
        return HTMLResponse(
            f'Failed to create order: {e}', status_code=code.INTERNAL_SERVER_ERROR
        )

    await CartService.clear_cart(cart_repo=cart_repo, session_id=session_id)
    return RedirectResponse('/', status_code=code.FOUND)


@router.get('/orders', response_class=HTMLResponse)
async def orders_view(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
):
    cashier_id = request.session.get('cashier_id')
    if not cashier_id:
        return RedirectResponse('/', status_code=code.FOUND)

    assert uow.orders is not None
    rows = await uow.orders.cashier_rows(cashier_id=cashier_id)

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

    today_key = date.today().isoformat()
    today_orders = grouped.get(today_key, [])

    return templates.TemplateResponse(
        'orders.html',
        {
            'request': request,
            'today_orders': today_orders,
        },
    )


@router.get('/orders/archive', response_class=HTMLResponse)
async def orders_archive_view(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
):
    cashier_id = request.session.get('cashier_id')
    if not cashier_id:
        return RedirectResponse('/', status_code=code.FOUND)

    assert uow.orders is not None
    rows = await uow.orders.cashier_rows(cashier_id=cashier_id)

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

    today_key = date.today().isoformat()
    # Keep only orders from yesterday and older (dates less than today)
    past_orders = {
        k: v for k, v in grouped.items() 
        if k < today_key  # This will keep all dates before today
    }

    return templates.TemplateResponse(
        'orders_archive.html',
        {
            'request': request,
            'archive_orders': past_orders,  # Now contains only past orders
        },
    )

@router.get('/orders/future', response_class=HTMLResponse)
async def orders_future_view(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
):
    cashier_id = request.session.get('cashier_id')
    if not cashier_id:
        return RedirectResponse('/', status_code=code.FOUND)

    assert uow.orders is not None
    rows = await uow.orders.cashier_rows(cashier_id=cashier_id)

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

    today_key = date.today().isoformat()
    # Keep only orders from tomorrow and future (tomorrow and newer)
    future_orders = {
        k: v for k, v in grouped.items() 
        if k > today_key  # This will keep all dates after today
    }

    return templates.TemplateResponse(
        'orders_future.html',
        {
            'request': request,
            'future_orders': future_orders,
        },
    )