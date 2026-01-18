from app.infrastructure.uow import AsyncpgUnitOfWork


class AuthService:
    @staticmethod
    async def ensure_admin(*, uow: AsyncpgUnitOfWork, cashier_id: str | None) -> bool:
        if not cashier_id:
            return False
        assert uow.cashiers is not None
        return await uow.cashiers.is_admin(cashier_id=cashier_id)

    @staticmethod
    async def cashier_exists(*, uow: AsyncpgUnitOfWork, cashier_id: str) -> bool:
        assert uow.cashiers is not None
        return await uow.cashiers.exists(cashier_id=cashier_id)