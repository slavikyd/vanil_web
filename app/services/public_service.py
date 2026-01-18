from app.infrastructure.uow import AsyncpgUnitOfWork


class PublicService:
    @staticmethod
    async def list_active_items(*, uow: AsyncpgUnitOfWork) -> list[dict]:
        assert uow.items is not None
        return await uow.items.list_active()
