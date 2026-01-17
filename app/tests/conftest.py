import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient
from httpx._transports.asgi import ASGITransport

from app.main import app

# Ensure test schema flag is set for the app
os.environ.setdefault("DB_SCHEMA", "test")


@pytest.fixture(scope="session")
def event_loop():
    """Dedicated event loop for async tests."""
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db_pool():
    """
    Fully mocked asyncpg pool + connection.

    Any code that does:
        pool = await connect_db()
        async with pool.acquire() as conn:
            await conn.fetch(...)
    will work against this mock without hitting a real DB.
    """
    pool = AsyncMock(name="mock_pool")
    conn = AsyncMock(name="mock_conn")

    # Generic asyncpg‑like methods
    conn.execute = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetchval = AsyncMock(return_value=None)

    # Context manager for pool.acquire()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=acquire_cm)

    pool.close = AsyncMock(return_value=None)

    return pool, conn


@pytest.fixture
def mock_redis(monkeypatch):
    """Mock Redis client so no real Redis is needed."""
    redis = AsyncMock(name="mock_redis")
    redis.hgetall = AsyncMock(return_value={})
    redis.hset = AsyncMock(return_value=1)
    redis.hdel = AsyncMock(return_value=1)
    redis.delete = AsyncMock(return_value=None)
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.close = AsyncMock(return_value=None)

    monkeypatch.setattr("app.redis.redis", redis)
    return redis


@pytest.fixture
async def client(mock_db_pool, mock_redis, monkeypatch):
    """Create test client with mocked dependencies."""
    pool, conn = mock_db_pool

    # Patch redis at the source before any modules import it
    monkeypatch.setattr("app.redis.redis", mock_redis)
    
    # Also patch in modules that imported it
    monkeypatch.setattr("app.services.cart_service.redis", mock_redis)
    monkeypatch.setattr("app.routes.crud_routes.redis", mock_redis)
    monkeypatch.setattr("app.routes.extra_routes.redis", mock_redis)

    with patch("app.db.connect_db", return_value=pool):
        with patch("app.main.connect_db", return_value=pool):
            app.state.db = pool
            app.state.cart = {"items": {}}

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac

