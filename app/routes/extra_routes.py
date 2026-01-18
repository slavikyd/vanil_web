from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.infrastructure.redis.cart_repo import RedisCartRepo
from app.infrastructure.uow import AsyncpgUnitOfWork
from app.routes.deps import get_cart_repo, get_uow
from app.routes.session_utils import get_or_create_session_id
from app.services.auth_service import AuthService
from app.services.cart_service import CartService
from app.services.index_service import IndexService
from app.settings.config import templates

router = APIRouter(tags=["auth", "main"])


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
    cart_repo: RedisCartRepo = Depends(get_cart_repo),
):
    cashier_id = request.session.get("cashier_id")
    if not cashier_id:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "cashier_id": None},
        )

    session_id = get_or_create_session_id(request.session)

    ctx = await IndexService.get_index_context(
        uow=uow,
        cart_repo=cart_repo,
        cashier_id=cashier_id,
        session_id=session_id,
    )
    return templates.TemplateResponse("index.html", {"request": request, **ctx})


@router.post("/login")
async def login(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
    cashier_id: str = Form(...),
):
    ok = await AuthService.cashier_exists(uow=uow, cashier_id=cashier_id)
    if not ok:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "cashier_id": None, "error": "Invalid cashier ID"},
        )

    request.session["cashier_id"] = cashier_id
    get_or_create_session_id(request.session)

    return RedirectResponse("/", status_code=302)


@router.post("/logout")
async def logout(
    request: Request,
    cart_repo: RedisCartRepo = Depends(get_cart_repo),
):
    session_id = request.session.get("session_id")
    if session_id:
        await CartService.clear_cart(cart_repo=cart_repo, session_id=session_id)

    request.session.clear()
    return RedirectResponse("/", status_code=302)


@router.get("/api/data", response_class=JSONResponse)
async def get_data_json(
    request: Request,
    uow: AsyncpgUnitOfWork = Depends(get_uow),
    cart_repo: RedisCartRepo = Depends(get_cart_repo),
):
    cashier_id = request.session.get("cashier_id")
    if not cashier_id:
        return JSONResponse({"error": "Not logged in"}, status_code=401)

    session_id = get_or_create_session_id(request.session)

    data = await IndexService.get_api_data(
        uow=uow,
        cart_repo=cart_repo,
        cashier_id=cashier_id,
        session_id=session_id,
    )
    return JSONResponse(data)
