import logging
import uuid
from datetime import date, timedelta

from app.infrastructure.redis.cart_repo import RedisCartRepo
from app.infrastructure.uow import AsyncpgUnitOfWork
from app.services.order_service import OrderService, EmptyCartError, InvalidOrderDateError

logger = logging.getLogger(__name__)


async def finalize_abandoned_carts(db_pool) -> None:
    """
    Scans all active cart sessions in Redis. For each cart that has a shop_id
    set, creates an order from its contents (defaulting order_for to tomorrow
    and shipment to 1 if not otherwise available), then clears the cart.
    Carts with no shop_id are skipped.
    """
    cart_repo = RedisCartRepo()
    session_ids = await cart_repo.list_all_cart_session_ids()

    logger.info('cart_finalizer_start', extra={'session_count': len(session_ids)})

    finalized = 0
    skipped = 0

    for session_id in session_ids:
        try:
            cart = await cart_repo.get_cart(session_id=session_id)
            if not cart:
                continue

            meta = await cart_repo.get_meta(session_id=session_id)
            shop_id = meta.get('shop_id')
            cashier_id = meta.get('cashier_id')

            if not shop_id:
                skipped += 1
                logger.info('cart_finalizer_skip_no_shop', extra={'session_id': session_id})
                continue

            comments = await cart_repo.get_comments(session_id=session_id)
            order_types = await cart_repo.get_order_types(session_id=session_id)

            order_for = (date.today() + timedelta(days=1)).isoformat()
            shipment = 1

            async with AsyncpgUnitOfWork(db_pool) as uow:
                await OrderService.create_order(
                    uow=uow,
                    cashier_id=cashier_id or 'unknown',
                    shop_id=uuid.UUID(shop_id),
                    cart=cart,
                    order_for=order_for,
                    comment=None,
                    comments=comments,
                    order_types=order_types,
                    shipment=shipment,
                )

            await cart_repo.clear(session_id=session_id)
            finalized += 1
            logger.info(
                'cart_finalizer_order_created',
                extra={'session_id': session_id, 'shop_id': shop_id, 'cashier_id': cashier_id},
            )

        except (EmptyCartError, InvalidOrderDateError) as e:
            logger.warning('cart_finalizer_order_failed', extra={'session_id': session_id, 'error': str(e)})
        except Exception as e:
            logger.exception('cart_finalizer_unexpected_error', extra={'session_id': session_id, 'error': str(e)})

    logger.info('cart_finalizer_done', extra={'finalized': finalized, 'skipped': skipped})