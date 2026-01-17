"""
Admin роуты (финальная версия)
"""
import uuid
from datetime import date
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from app.services.admin_service import AdminService  # Только AdminService
from app.services.auth_service import AuthService
from app.settings.config import templates

router = APIRouter(prefix="/admin", tags=["admin"])

@router.post("/items/create")
async def create_item(request: Request, name: str = Form(...), price: float = Form(...), ttl: int = Form(...)):
    if not await AuthService.ensure_admin(request):
        return RedirectResponse("/", status_code=302)
    await AdminService.create_item(request.app.state.db, name, price, ttl)
    return RedirectResponse("/admin/items", status_code=302)

@router.post("/items/delete")
async def delete_item(request: Request, itemid: str = Form(...)):
    if not await AuthService.ensure_admin(request):
        return RedirectResponse("/", status_code=302)
    await AdminService.delete_item(request.app.state.db, uuid.UUID(itemid))
    return RedirectResponse("/admin/items", status_code=302)

@router.get("/items", response_class=HTMLResponse)
async def admin_items(request: Request):
    if not await AuthService.ensure_admin(request):
        return RedirectResponse("/", status_code=302)
    items = await AdminService.list_items(request.app.state.db)
    return templates.TemplateResponse("admin_items.html", {
        "request": request, 
        "items": items
    })

@router.post("/items/toggle")
async def toggle_items(request: Request):
    if not await AuthService.ensure_admin(request):
        return RedirectResponse("/", status_code=302)
    
    form = await request.form()
    # ✅ БИЗНЕС ВЫНЕСЕН (parse_toggle_form вызывается ИЗ admin_service)
    await AdminService.toggle_items_form(request.app.state.db, form)
    return RedirectResponse("/admin/items", status_code=302)

# Остальные роуты (orders/export) БЕЗ ИЗМЕНЕНИЙ
@router.get("/orders", response_class=HTMLResponse)
async def admin_orders(request: Request):
    if not await AuthService.ensure_admin(request):
        return RedirectResponse("/", status_code=302)
    grouped = await AdminService.get_orders(
        request.app.state.db, 
        request.query_params.get("order_for_date"), 
        request.query_params.get("address")
    )
    return templates.TemplateResponse("admin_orders.html", {
        "request": request, 
        "grouped_orders": grouped, 
        "order_for": request.query_params.get("order_for_date"),
        "address": request.query_params.get("address")
    })

@router.post("/orders/delete")
async def delete_order(request: Request, orderid: str = Form(...)):
    if not await AuthService.ensure_admin(request):
        return RedirectResponse("/", status_code=302)
    ok = await AdminService.delete_order(request.app.state.db, uuid.UUID(orderid))
    return RedirectResponse("/admin/orders", status_code=302 if ok else 404)


@router.get('/orders/export')
async def export_orders(request: Request, address: str | None = None):
    if not await AuthService.ensure_admin(request):
        return RedirectResponse('/', 302)

    stream = await AdminService.export_orders(
        request.app.state.db, address
    )
    return StreamingResponse(
        stream,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename=orders.xlsx'},
    )


@router.get('/export/by_address')
async def export_by_address(request: Request, order_for: date):
    if not await AuthService.ensure_admin(request):
        return RedirectResponse('/', 302)

    stream = await AdminService.export_by_address(
        request.app.state.db, order_for
    )
    return StreamingResponse(
        stream,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={
            'Content-Disposition': f'attachment; filename=by_address_{order_for}.xlsx'
        },
    )
