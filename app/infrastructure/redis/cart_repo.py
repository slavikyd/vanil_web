import logging

from app.redis import redis

CART_TTL_SECONDS = 1800
logger = logging.getLogger(__name__)


class RedisCartRepo:
    def _key(self, session_id: str) -> str:
        return f'cart:{session_id}'

    async def get_cart(self, *, session_id: str) -> dict[str, int]:
        try:
            raw = await redis.hgetall(self._key(session_id))
            return {k: int(v) for k, v in raw.items()}
        except Exception as e:
            logger.warning(f'Failed to read cart from Redis: {e}')
            return {}

    async def set_item(self, *, session_id: str, item_id: str, quantity: int) -> None:
        key = self._key(session_id)
        try:
            if quantity > 0:
                await redis.hset(key, item_id, quantity)
                await redis.expire(key, CART_TTL_SECONDS)
            else:
                await redis.hdel(key, item_id)
        except Exception as e:
            logger.warning(f'Failed to update cart in Redis: {e}')

    async def clear(self, *, session_id: str) -> None:
        try:
            await redis.delete(self._key(session_id))
        except Exception as e:
            logger.warning(f'Failed to clear cart in Redis: {e}')
