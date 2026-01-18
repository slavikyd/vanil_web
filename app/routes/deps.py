from typing import AsyncIterator
from fastapi import Request

from app.infrastructure.redis.cart_repo import RedisCartRepo
from app.infrastructure.uow import AsyncpgUnitOfWork


async def get_uow(request: Request) -> AsyncIterator[AsyncpgUnitOfWork]:
    async with AsyncpgUnitOfWork(request.app.state.db) as uow:
        yield uow


def get_cart_repo() -> RedisCartRepo:
    return RedisCartRepo()