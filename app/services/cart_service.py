from app.constants import MAX_ITEM_COMMENT_LENGTH
from app.infrastructure.redis.cart_repo import RedisCartRepo


class CartService:
    @staticmethod
    async def get_cart(*, cart_repo: RedisCartRepo, session_id: str) -> dict[str, int]:
        return await cart_repo.get_cart(session_id=session_id)

    @staticmethod
    async def get_comments(*, cart_repo: RedisCartRepo, session_id: str) -> dict[str, str]:
        return await cart_repo.get_comments(session_id=session_id)

    @staticmethod
    async def set_item(
        *, cart_repo: RedisCartRepo, session_id: str, item_id: str, quantity: int
    ) -> None:
        await cart_repo.set_item(
            session_id=session_id, item_id=item_id, quantity=quantity
        )

    @staticmethod
    async def set_comment(
        *, cart_repo: RedisCartRepo, session_id: str, item_id: str, comment: str
    ) -> None:
        text = (comment or '').strip()[:MAX_ITEM_COMMENT_LENGTH]
        await cart_repo.set_comment(
            session_id=session_id, item_id=item_id, comment=text
        )

    @staticmethod
    async def clear_cart(*, cart_repo: RedisCartRepo, session_id: str) -> None:
        await cart_repo.clear(session_id=session_id)
