from typing import Any, Dict

from app.infrastructure.redis.cart_repo import RedisCartRepo
from app.infrastructure.uow import AsyncpgUnitOfWork
from app.services.auth_service import AuthService
from app.services.cart_service import CartService
from app.services.public_service import PublicService


class IndexService:
    @staticmethod
    async def get_index_context(
        *,
        uow: AsyncpgUnitOfWork,
        cart_repo: RedisCartRepo,
        cashier_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        items = await PublicService.list_active_items(uow=uow)
        cart = await CartService.get_cart(cart_repo=cart_repo, session_id=session_id)
        is_admin = await AuthService.ensure_admin(uow=uow, cashier_id=cashier_id)

        return {
            'items': items,
            'cart': cart,
            'cashier_id': cashier_id,
            'is_admin': is_admin,
        }

    @staticmethod
    async def get_api_data(
        *,
        uow: AsyncpgUnitOfWork,
        cart_repo: RedisCartRepo,
        cashier_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        items = await PublicService.list_active_items(uow=uow)
        cart = await CartService.get_cart(cart_repo=cart_repo, session_id=session_id)
        is_admin = await AuthService.ensure_admin(uow=uow, cashier_id=cashier_id)

        return {
            'items': items,
            'cart': cart,
            'is_admin': is_admin,
        }
