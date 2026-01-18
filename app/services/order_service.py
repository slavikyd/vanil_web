import uuid
from datetime import datetime

from app.infrastructure.uow import AsyncpgUnitOfWork


class EmptyCartError(Exception):
    pass


class InvalidOrderDateError(Exception):
    pass


class OrderService:
    @staticmethod
    async def create_order(
        *,
        uow: AsyncpgUnitOfWork,
        cashier_id: str,
        shop_id: str | None,
        cart: dict[str, int],
        order_for: str,
    ) -> uuid.UUID:
        if not cart:
            raise EmptyCartError()

        try:
            order_for_date = datetime.strptime(order_for, "%Y-%m-%d").date()
        except ValueError:
            raise InvalidOrderDateError()

        if not shop_id:
            raise ValueError("Shop id is required")

        assert uow.shops is not None
        assert uow.orders is not None

        order_id = uuid.uuid4()

        async with uow.transaction():
            address = await uow.shops.get_address(shop_id=shop_id)
            if not address:
                raise ValueError("Shop not found")

            await uow.orders.create_order(
                order_id=order_id,
                cashier_id=cashier_id,
                shop_id=shop_id,
                address=address,
                order_for=order_for_date,
            )
            await uow.orders.add_items(order_id=order_id, cart=cart)

        return order_id