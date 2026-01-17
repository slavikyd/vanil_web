import uuid
from typing import Dict

from app.redis import redis

CART_TTL_SECONDS = 1800


def cart_key(session_id: str) -> str:
    return f"cart:{session_id}"


def get_or_create_session_id(request) -> str:
    """
    Единый источник истины для корзины.
    Работает и в браузере, и в TG WebApp.
    """
    session_id = request.session.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        request.session["session_id"] = session_id
    return session_id


async def get_cart(session_id: str) -> Dict[str, int]:
    raw = await redis.hgetall(cart_key(session_id))
    return {k: int(v) for k, v in raw.items()}


async def set_item(session_id: str, item_id: str, quantity: int) -> None:
    key = cart_key(session_id)

    if quantity > 0:
        await redis.hset(key, item_id, quantity)
        await redis.expire(key, CART_TTL_SECONDS)
    else:
        await redis.hdel(key, item_id)


async def clear_cart(session_id: str) -> None:
    await redis.delete(cart_key(session_id))
