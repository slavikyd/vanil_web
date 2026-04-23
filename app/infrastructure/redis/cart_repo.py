import logging
import os
from app.redis import redis

logger = logging.getLogger(__name__)
CART_TTL_SECONDS = int(os.getenv('SESSION_MAX_AGE_SECONDS'))

class RedisCartRepo:
    def _key(self, session_id: str) -> str:
        return f'cart:{session_id}'

    def _comments_key(self, session_id: str) -> str:
        return f'cart_comments:{session_id}'

    async def get_cart(self, *, session_id: str) -> dict[str, int]:
        try:
            raw = await redis.hgetall(self._key(session_id))
            return {k: int(v) for k, v in raw.items()}
        except Exception as e:
            logger.warning(f'Failed to read cart from Redis: {e}')
            return {}

    async def get_comments(self, *, session_id: str) -> dict[str, str]:
        try:
            raw = await redis.hgetall(self._comments_key(session_id))
            return {k: str(v) for k, v in raw.items()}
        except Exception as e:
            logger.warning(f'Failed to read cart comments from Redis: {e}')
            return {}

    async def set_item(self, *, session_id: str, item_id: str, quantity: int) -> None:
        key = self._key(session_id)
        ck = self._comments_key(session_id)
        try:
            if quantity > 0:
                await redis.hset(key, item_id, quantity)
                await redis.expire(key, CART_TTL_SECONDS)
                await redis.expire(ck, CART_TTL_SECONDS)
            else:
                await redis.hdel(key, item_id)
                await redis.hdel(ck, item_id)
        except Exception as e:
            logger.warning(f'Failed to update cart in Redis: {e}')

    async def set_comment(self, *, session_id: str, item_id: str, comment: str) -> None:
        key = self._key(session_id)
        ck = self._comments_key(session_id)
        try:
            if not comment:
                await redis.hdel(ck, item_id)
            else:
                await redis.hset(ck, item_id, comment)
                await redis.expire(ck, CART_TTL_SECONDS)
            await redis.expire(key, CART_TTL_SECONDS)
        except Exception as e:
            logger.warning(f'Failed to update cart comment in Redis: {e}')

    async def clear(self, *, session_id: str) -> None:
        try:
            await redis.delete(self._key(session_id))
            await redis.delete(self._comments_key(session_id))
        except Exception as e:
            logger.warning(f'Failed to clear cart in Redis: {e}')
