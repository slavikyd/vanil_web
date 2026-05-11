import uuid
from datetime import datetime

from app.infrastructure.uow import AsyncpgUnitOfWork


class EmptyCartError(Exception):
    pass


class InvalidOrderDateError(Exception):
    pass


class OrderService:
    DEFAULT_TEST_ADDRESS = 'Тестовая улица 1'

    @staticmethod
    async def create_order(
        *,
        uow: AsyncpgUnitOfWork,
        cashier_id: str,
        shop_id: str | None,
        cart: dict[str, int],
        order_for: str,
        store_name: str | None = None,
        comments: dict[str, str] | None = None,
    ) -> uuid.UUID:
        if not cart:
            raise EmptyCartError()

        try:
            order_for_date = datetime.strptime(order_for, '%Y-%m-%d').date()
        except ValueError:
            raise InvalidOrderDateError()

        assert uow.orders is not None

        order_id = uuid.uuid4()
        address = (store_name or '').strip() or OrderService.DEFAULT_TEST_ADDRESS

        async with uow.transaction():
            await uow.orders.create_order(
                order_id=order_id,
                cashier_id=cashier_id,
                shop_id=shop_id,
                address=address,
                order_for=order_for_date,
            )
            await uow.orders.add_items(
                order_id=order_id, cart=cart, comments=comments
            )

        return order_id
