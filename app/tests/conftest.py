import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from httpx._transports.asgi import ASGITransport

from app.main import app

# Чтобы SessionMiddleware не падал из-за пустого secret_key в тестах
os.environ.setdefault("SESSION_SECRET_KEY", "test-secret")

# (Опционально) если где-то используется schema flag
os.environ.setdefault("DBSCHEMA", "test")


@pytest.fixture(scope="session")
def event_loop():
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db_pool():
    """
    Fully mocked asyncpg pool + connection.
    """
    pool = AsyncMock(name="mock_pool")
    conn = AsyncMock(name="mock_conn")

    # asyncpg-like methods
    conn.execute = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=None)

    # transaction() context manager (нужно для order_service.create_order)
    tx_cm = MagicMock()
    tx_cm.__aenter__ = AsyncMock(return_value=None)
    tx_cm.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx_cm)

    # pool.acquire() context manager
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)

    pool.acquire = MagicMock(return_value=acquire_cm)
    pool.close = AsyncMock(return_value=None)

    return pool, conn


@pytest.fixture
def mock_redis(monkeypatch):
    redis = AsyncMock(name="mock_redis")

    redis.hgetall = AsyncMock(return_value={})
    redis.hset = AsyncMock(return_value=1)
    redis.hdel = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=None)

    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.close = AsyncMock(return_value=None)

    monkeypatch.setattr("app.redis.redis", redis)
    return redis


@pytest.fixture
async def client(mock_db_pool, mock_redis, monkeypatch):
    pool, _ = mock_db_pool

    # Patch redis at the source
    monkeypatch.setattr("app.redis.redis", mock_redis)

    # Patch modules that imported redis
    monkeypatch.setattr("app.services.cart_service.redis", mock_redis)
    monkeypatch.setattr("app.routes.extra_routes.redis", mock_redis)

    # crud_routes.py может не иметь `redis` как атрибут — не падаем
    monkeypatch.setattr("app.routes.crud_routes.redis", mock_redis, raising=False)

    with patch("app.db.connect_db", return_value=pool):
        with patch("app.main.connect_db", return_value=pool):
            app.state.db = pool
            app.state.cart = {"items": {}}

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac
