from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from datetime import date

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

def group_orders_by_day(rows: list[dict]) -> dict[str, list[dict]]:
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
    return grouped

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
    comments = await CartService.get_comments(
        cart_repo=cart_repo, session_id=session_id
    )
    items_data = await PublicService.list_active_items(uow=uow)

    return JSONResponse(
        {'cart': cart, 'comments': comments, 'items_data': items_data}
    )


@router.post('/set-cart-comment')
async def set_cart_comment(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
    cart_repo: RedisCartRepo = Depends(get_cart_repo),
    itemid: str = Form(...),
    comment: str = Form(''),
):
    session_id = get_or_create_session_id(request.session)
    await CartService.set_comment(
        cart_repo=cart_repo,
        session_id=session_id,
        item_id=itemid,
        comment=comment,
    )
    cart = await CartService.get_cart(cart_repo=cart_repo, session_id=session_id)
    comments = await CartService.get_comments(
        cart_repo=cart_repo, session_id=session_id
    )
    items_data = await PublicService.list_active_items(uow=uow)
    return JSONResponse(
        {'cart': cart, 'comments': comments, 'items_data': items_data}
    )


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
        quantity=0, #TODO remove the magic number
    )
    return RedirectResponse('/', status_code=status.HTTP_302_FOUND) 


@router.post('/place_order')
async def place_order(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
    cart_repo: RedisCartRepo = Depends(get_cart_repo),
    order_for: str = Form(...),
    store_name: str | None = Form(None),
    tg_id: str | None = Form(None), #TODO: DERPRACATED
    comment: str | None = Form(None),
):
    session = request.session

    cashier_id = session.get('cashier_id')
    if not cashier_id:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)

    session_id = session.get('session_id')
    if not session_id:
        return HTMLResponse('Invalid session', status_code=status.HTTP_400_BAD_REQUEST)

    # Temporarily decouple order creation from Telegram shop id.
    shop_id = None

    cart = await CartService.get_cart(cart_repo=cart_repo, session_id=session_id)
    comments = await CartService.get_comments(
        cart_repo=cart_repo, session_id=session_id
    )

    try:
        await OrderService.create_order(
            uow=uow,
            cashier_id=cashier_id,
            shop_id=shop_id,
            cart=cart,
            order_for=order_for,
            store_name=store_name,
            comment=comment,
            comments=comments,
        )
    except EmptyCartError:
        return HTMLResponse('Cart is empty', status_code=status.HTTP_400_BAD_REQUEST)
    except InvalidOrderDateError:
        return HTMLResponse('Invalid order date', status_code=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return HTMLResponse(
            f'Failed to create order: {e}', status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    await CartService.clear_cart(cart_repo=cart_repo, session_id=session_id)
    return RedirectResponse('/', status_code=status.HTTP_302_FOUND)


@router.get('/orders', response_class=HTMLResponse)
async def orders_view(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
):
    cashier_id = request.session.get('cashier_id')
    if not cashier_id:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)

    assert uow.orders is not None
    rows = await uow.orders.cashier_rows(cashier_id=cashier_id, date_filter='today')
    grouped = group_orders_by_day(rows)
    today_orders = grouped.get(date.today().isoformat(), [])
    return templates.TemplateResponse(
        'orders.html',
        {'request': request, 'today_orders': today_orders},
    )


@router.get('/orders/archive', response_class=HTMLResponse)
async def orders_archive_view(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
):
    cashier_id = request.session.get('cashier_id')
    if not cashier_id:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)

    assert uow.orders is not None
    rows = await uow.orders.cashier_rows(cashier_id=cashier_id, date_filter='past')
    grouped = group_orders_by_day(rows)
    return templates.TemplateResponse(
        'orders_archive.html',
        {'request': request, 'archive_orders': grouped},
    )

@router.get('/orders/future', response_class=HTMLResponse)
async def orders_future_view(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
):
    cashier_id = request.session.get('cashier_id')
    if not cashier_id:
        return RedirectResponse('/', status_code=status.HTTP_302_FOUND)

    assert uow.orders is not None

    rows = await uow.orders.cashier_rows(cashier_id=cashier_id, date_filter='future')
    grouped = group_orders_by_day(rows)

    return templates.TemplateResponse(
        'orders_future.html',
        {'request': request, 'future_orders': grouped},
    )