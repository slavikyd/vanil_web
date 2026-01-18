from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from asyncpg import Connection, Pool

from app.infrastructure.repos.cashiers_repo import CashiersRepo
from app.infrastructure.repos.items_repo import ItemsRepo
from app.infrastructure.repos.orders_repo import OrdersRepo
from app.infrastructure.repos.shops_repo import ShopsRepo


@dataclass
class AsyncpgUnitOfWork:
    pool: Pool
    conn: Optional[Connection] = None

    items: ItemsRepo | None = None
    cashiers: CashiersRepo | None = None
    shops: ShopsRepo | None = None
    orders: OrdersRepo | None = None

    async def __aenter__(self) -> "AsyncpgUnitOfWork":
        self.conn = await self.pool.acquire()
        self.items = ItemsRepo(self.conn)
        self.cashiers = CashiersRepo(self.conn)
        self.shops = ShopsRepo(self.conn)
        self.orders = OrdersRepo(self.conn)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        assert self.conn is not None
        await self.pool.release(self.conn)
        self.conn = None
        self.items = None
        self.cashiers = None
        self.shops = None
        self.orders = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        assert self.conn is not None
        async with self.conn.transaction():
            yield
