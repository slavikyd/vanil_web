"""
Extra routes for authentication and main page.
"""

import uuid

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.redis import redis
from app.services.index_service import get_api_data, get_index_context
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

    ctx = await get_index_context(request)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, **ctx},
    )


@router.post("/login")
async def login(request: Request, cashier_id: str = Form(...)):
    # НЕ ТРОГАЕМ логику логина: как было — проверка кассира и установка сессии.
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
    # НЕ ТРОГАЕМ логику логаута: как было — удалить корзину и очистить сессию.
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

    data = await get_api_data(request)
    # get_api_data() возвращает {"error": "..."} только если не залогинен,
    # но этот кейс уже отфильтрован выше.
    return JSONResponse(data)
