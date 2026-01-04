"""Extra routes for authentication and main page.

Includes endpoints for:
- Login/logout
- Main index page
"""

import uuid

from app.settings.config import templates
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(tags=["auth", "main"])


def get_session_cart(router: APIRouter) -> dict:
    """Initialize cart storage if not present."""
    if not hasattr(router, "carts"):
        router.carts = {}
    return router.carts


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main index page. Shows items and cart if logged in."""
    cashier_id = request.session.get("cashier_id")
    
    if not cashier_id:
        return templates.TemplateResponse("index.html", {"request": request, "cashier_id": None})

    async with request.app.state.db.acquire() as conn:
        # Get all active items
        items = await conn.fetch("SELECT id, name, price FROM items WHERE active = TRUE ORDER BY name ASC")
        
        # Get cashier data to check admin status
        cashier_record = await conn.fetchrow("SELECT is_admin FROM cashiers WHERE id = $1", cashier_id)

    items_list_for_template = []
    for item in items:
        items_list_for_template.append({
            "id": str(item["id"]),
            "name": item["name"],
            "price": float(item["price"])
        })

    # Get or create session cart
    carts = get_session_cart(router)
    session_id = request.session.get("session_id")
    
    if not session_id or session_id not in carts:
        session_id = str(uuid.uuid4())
        carts[session_id] = {}
        request.session["session_id"] = session_id

    serializable_cart = {str(k): v for k, v in carts[session_id].items()}

    is_admin = False
    if cashier_record:
        is_admin = cashier_record["is_admin"]

    return templates.TemplateResponse("index.html", {
        "request": request,
        "items": items_list_for_template,
        "cart": serializable_cart,
        "cashier_id": cashier_id,
        "is_admin": is_admin,
    })


@router.post("/login")
async def login(request: Request, cashier_id: str = Form(...)):
    """Login with cashier ID."""
    async with request.app.state.db.acquire() as conn:
        cashier = await conn.fetchrow("SELECT id FROM cashiers WHERE id = $1", cashier_id)
        if not cashier:
            return templates.TemplateResponse("index.html", {"request": request, "cashier_id": None, "error": "Invalid cashier ID"})
    
    request.session["cashier_id"] = cashier_id
    session_id = str(uuid.uuid4())
    
    carts = get_session_cart(router)
    carts[session_id] = {}
    request.session["session_id"] = session_id
    
    return RedirectResponse("/", status_code=302)


@router.post("/logout")
async def logout(request: Request):
    """Logout and clear session."""
    session_id = request.session.get("session_id")
    carts = get_session_cart(router)
    
    if session_id in carts:
        del carts[session_id]
    
    request.session.clear()
    return RedirectResponse("/", status_code=302)
