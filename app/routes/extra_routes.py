"""
Extra routes for authentication and main page.
"""

import uuid

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from app.redis import redis
from app.settings.config import templates

router = APIRouter(tags=["auth", "main"])


def cart_key(session_id: str) -> str:
    return f"cart:{session_id}"


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    cashier_id = request.session.get("cashier_id")

    if not cashier_id:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "cashier_id": None},
        )

    # session id is REQUIRED
    session_id = request.session.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        request.session["session_id"] = session_id

    # fetch cart from redis
    cart = await redis.hgetall(cart_key(session_id))
    cart = {k: int(v) for k, v in cart.items()}

    async with request.app.state.db.acquire() as conn:
        items = await conn.fetch(
            "SELECT id, name, price FROM items WHERE active = TRUE ORDER BY name ASC"
        )
        cashier = await conn.fetchrow(
            "SELECT is_admin FROM cashiers WHERE id = $1",
            cashier_id,
        )

    items_list = [
        {"id": str(i["id"]), "name": i["name"], "price": float(i["price"])}
        for i in items
    ]

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "items": items_list,
            "cart": cart,
            "cashier_id": cashier_id,
            "is_admin": cashier["is_admin"] if cashier else False,
        },
    )


@router.post("/login")
async def login(request: Request, cashier_id: str = Form(...)):
    async with request.app.state.db.acquire() as conn:
        cashier = await conn.fetchrow(
            "SELECT id FROM cashiers WHERE id = $1",
            cashier_id,
        )
        if not cashier:
            return templates.TemplateResponse(
                "index.html",
                {
                    "request": request,
                    "cashier_id": None,
                    "error": "Invalid cashier ID",
                },
            )

    request.session["cashier_id"] = cashier_id
    request.session["session_id"] = str(uuid.uuid4())

    return RedirectResponse("/", status_code=302)


@router.post("/logout")
async def logout(request: Request):
    session_id = request.session.get("session_id")
    if session_id:
        await redis.delete(cart_key(session_id))

    request.session.clear()
    return RedirectResponse("/", status_code=302)


@router.get("/api/data", response_class=JSONResponse)
async def get_data_json(request: Request):
    cashier_id = request.session.get("cashier_id")
    if not cashier_id:
        return JSONResponse({"error": "Not logged in"}, status_code=401)

    async with request.app.state.db.acquire() as conn:
        items = await conn.fetch(
            "SELECT id, name, price FROM items WHERE active = TRUE ORDER BY name ASC"
        )
        cashier = await conn.fetchrow(
            "SELECT is_admin FROM cashiers WHERE id = $1",
            cashier_id,
        )

    return JSONResponse(
        {
            "items": [
                {"id": str(i["id"]), "name": i["name"], "price": float(i["price"])}
                for i in items
            ],
            "is_admin": cashier["is_admin"] if cashier else False,
        }
    )
