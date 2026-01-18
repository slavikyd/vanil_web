from app.redis import redis

CART_TTL_SECONDS = 1800


class RedisCartRepo:
    def _key(self, session_id: str) -> str:
        return f'cart:{session_id}'

    async def get_cart(self, *, session_id: str) -> dict[str, int]:
        raw = await redis.hgetall(self._key(session_id))
        return {k: int(v) for k, v in raw.items()}

    async def set_item(self, *, session_id: str, item_id: str, quantity: int) -> None:
        key = self._key(session_id)
        if quantity > 0:
            await redis.hset(key, item_id, quantity)
            await redis.expire(key, CART_TTL_SECONDS)
        else:
            await redis.hdel(key, item_id)

    async def clear(self, *, session_id: str) -> None:
        await redis.delete(self._key(session_id))
