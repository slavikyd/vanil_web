"""Admin's routes."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

import app.http_codes as code
from app.infrastructure.uow import AsyncpgUnitOfWork
from app.routes.deps import get_uow
from app.services.admin_service import AdminService
from app.services.auth_service import AuthService
from app.settings.config import templates

router = APIRouter(prefix='/admin', tags=['admin'])


async def _ensure_admin_or_redirect(request: Request, uow: AsyncpgUnitOfWork) -> bool:
    cashier_id = request.session.get('cashier_id')
    return await AuthService.ensure_admin(uow=uow, cashier_id=cashier_id)


@router.post('/items/create')
async def create_item(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
    name: str = Form(...),
    price: float = Form(...),
    ttl: int = Form(...),
):
    """Item entity creation endpoint

    Args:
        request (Request): request
        uow (AsyncpgUnitOfWork, optional): unit of work. Defaults to Depends(get_uow).
        name (str, optional): name of the new item. Defaults to Form(...).
        price (float, optional): item's price. Defaults to Form(...).
        ttl (int, optional): time to life of the item. Defaults to Form(...).

    Returns:
        RedirectResponse: onto the /admin/items endpoint and status code 302 FOUND
    """
    if not await _ensure_admin_or_redirect(request, uow):
        return RedirectResponse('/', status_code=code.FOUND)

    await AdminService.create_item(uow=uow, name=name, price=price, ttl=ttl)
    return RedirectResponse('/admin/items', status_code=code.FOUND)


@router.post('/items/delete')
async def delete_item(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
    item_id: str = Form(...),
):
    """Item entity deletion endpoint

    Args:
        request (Request): request
        uow (AsyncpgUnitOfWork, optional): unit of work. Defaults to Depends(get_uow).
        item_id (str, optional): id of the item to delete. Defaults to Form(...).

    Returns:
       RedirectResponse: onto the /admin/items endpoint and status code 302 FOUND
    """
    if not await _ensure_admin_or_redirect(request, uow):
        return RedirectResponse('/', status_code=code.FOUND)

    await AdminService.delete_item(uow=uow, item_id=uuid.UUID(item_id))
    return RedirectResponse('/admin/items', status_code=code.FOUND)


@router.get('/items', response_class=HTMLResponse)
async def admin_items(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
):
    """Items get endpoint

    Args:
        request (Request): request
        uow (AsyncpgUnitOfWork, optional): unit of work. Defaults to Depends(get_uow).

    Returns:
        admin html page with items: and status code 200 OK
    """
    if not await _ensure_admin_or_redirect(request, uow):
        return RedirectResponse('/', status_code=code.FOUND)

    items = await AdminService.list_items(uow=uow)
    return templates.TemplateResponse(
        'admin_items.html', {'request': request, 'items': items}
    )


@router.post('/items/toggle')
async def toggle_items(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
):
    if not await _ensure_admin_or_redirect(request, uow):
        return RedirectResponse('/', status_code=code.FOUND)

    form = await request.form()

    active_ids = {
        uuid.UUID(k.replace('active_', '')): True
        for k in form.keys()
        if k.startswith('active_')
    }

    all_items = await AdminService.list_items(uow=uow)
    active_map = {
        uuid.UUID(i['id']): bool(active_ids.get(uuid.UUID(i['id']), False))
        for i in all_items
    }

    await AdminService.toggle_items(uow=uow, active_map=active_map)
    return RedirectResponse('/admin/items', status_code=code.FOUND)


@router.get('/orders', response_class=HTMLResponse)
async def admin_orders(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
):
    if not await _ensure_admin_or_redirect(request, uow):
        return RedirectResponse('/', status_code=code.FOUND)

    order_for = request.query_params.get('order_for_date')
    address = request.query_params.get('address')

    grouped = await AdminService.get_orders(
        uow=uow, order_for=order_for, address=address
    )

    return templates.TemplateResponse(
        'admin_orders.html',
        {
            'request': request,
            'grouped_orders': grouped,
            'order_for': order_for,
            'address': address,
        },
    )


@router.post('/orders/delete')
async def delete_order(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
    order_id: str = Form(...),
):
    if not await _ensure_admin_or_redirect(request, uow):
        return RedirectResponse('/', status_code=code.FOUND)

    ok = await AdminService.delete_order(uow=uow, order_id=uuid.UUID(order_id))
    return RedirectResponse(
        '/admin/orders', status_code=(code.FOUND if ok else code.NOT_FOUND)
    )


@router.get('/orders/export')
async def export_orders(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
    address: str | None = None,
):
    if not await _ensure_admin_or_redirect(request, uow):
        return RedirectResponse('/', status_code=code.FOUND)

    stream = await AdminService.export_orders(uow=uow, address=address)
    return StreamingResponse(
        stream,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename=orders.xlsx'},
    )


@router.get('/export/by_address')
async def export_by_address(
    request: Request,
    order_for: date,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
):
    if not await _ensure_admin_or_redirect(request, uow):
        return RedirectResponse('/', status_code=code.FOUND)

    stream = await AdminService.export_by_address(uow=uow, order_for=order_for)
    return StreamingResponse(
        stream,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={
            'Content-Disposition': f'attachment; filename=by_address_{order_for}.xlsx'
        },
    )
