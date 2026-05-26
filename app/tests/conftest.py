import os
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from httpx import AsyncClient

try:
    from httpx import ASGITransport
except Exception:
    from httpx._transports.asgi import ASGITransport

from app.infrastructure.uow import AsyncpgUnitOfWork
from app.main import app
from app.routes.deps import get_cart_repo, get_uow

os.environ.setdefault('SESSION_SECRET_KEY', 'test-secret')
os.environ.setdefault('DBSCHEMA', 'test')
CART_TTL_SECONDS = int(os.getenv('SESSION_MAX_AGE_SECONDS'))

class FakeCartRepo:
    def __init__(self, redis):
        self._redis = redis
        self._comments: dict[str, dict[str, str]] = {}
        self._order_types: dict[str, dict[str, str]] = {}

    @staticmethod
    def _key(session_id: str) -> str:
        return f'cart:{session_id}'

    @staticmethod
    def _to_int(v) -> int:
        if isinstance(v, (bytes, bytearray)):
            return int(v.decode('utf-8'))
        return int(v)

    async def get_cart(self, *, session_id: str) -> dict[str, int]:
        raw = await self._redis.hgetall(self._key(session_id))
        return {str(k): self._to_int(v) for k, v in raw.items()}

    async def get_comments(self, *, session_id: str) -> dict[str, str]:
        return dict(self._comments.get(session_id, {}))

    async def set_item(self, *, session_id: str, item_id: str, quantity: int) -> None:
        key = self._key(session_id)
        if quantity > 0:
            await self._redis.hset(key, item_id, quantity)
            await self._redis.expire(key, CART_TTL_SECONDS)
        else:
            await self._redis.hdel(key, item_id)
            self._comments.get(session_id, {}).pop(str(item_id), None)

    async def set_comment(self, *, session_id: str, item_id: str, comment: str) -> None:
        bucket = self._comments.setdefault(session_id, {})
        if not comment:
            bucket.pop(str(item_id), None)
        else:
            bucket[str(item_id)] = comment
    async def get_order_types(self, *, session_id: str) -> dict[str, str]:
        return dict(self._order_types.get(session_id, {}))

    async def set_order_type(self, *, session_id: str, item_id: str, order_type: str) -> None:
        bucket = self._order_types.setdefault(session_id, {})
        bucket[str(item_id)] = order_type

    async def clear(self, *, session_id: str) -> None:
        await self._redis.delete(self._key(session_id))
        self._comments.pop(session_id, None)
        self._order_types.pop(session_id, None)



@pytest.fixture(scope='session')
def event_loop():
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db_pool():
    pool = AsyncMock(name='mock_pool')
    conn = AsyncMock(name='mock_conn')

    conn.execute = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=None)

    tx_cm = MagicMock()
    tx_cm.__aenter__ = AsyncMock(return_value=None)
    tx_cm.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx_cm)

    pool.acquire = AsyncMock(return_value=conn)
    pool.release = AsyncMock(return_value=None)
    pool.close = AsyncMock(return_value=None)

    return pool, conn


@pytest.fixture
def mock_redis():
    redis = AsyncMock(name='mock_redis')
    redis.hgetall = AsyncMock(return_value={})
    redis.hset = AsyncMock(return_value=1)
    redis.hdel = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=None)
    return redis


@pytest.fixture
async def client(mock_db_pool, mock_redis):
    pool, _ = mock_db_pool

    with patch('app.db.connect_db', new=AsyncMock(return_value=pool)):
        with patch('app.main.connect_db', new=AsyncMock(return_value=pool)):
            app.state.db = pool

            async def override_get_uow(
                request: Request,
            ) -> AsyncIterator[AsyncpgUnitOfWork]:
                async with AsyncpgUnitOfWork(request.app.state.db) as uow:
                    yield uow

            def override_get_cart_repo():
                return FakeCartRepo(mock_redis)

            app.dependency_overrides[get_uow] = override_get_uow
            app.dependency_overrides[get_cart_repo] = override_get_cart_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url='http://test') as ac:
                yield ac

            app.dependency_overrides = {}