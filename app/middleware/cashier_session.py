import logging
import os
import time

from starlette.middleware.base import BaseHTTPMiddleware

from app.infrastructure.redis.cart_repo import RedisCartRepo

logger = logging.getLogger(__name__)

SESSION_MAX_AGE_SECONDS = int(os.getenv('SESSION_MAX_AGE_SECONDS'))

class CashierSessionTimeoutMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request, call_next):
        session = request.session
        cashier_id = session.get('cashier_id')
        if cashier_id:
            login_at = session.get('login_at')
            now = int(time.time())
            if login_at is None or (now - int(login_at)) > SESSION_MAX_AGE_SECONDS:
                sid = session.get('session_id')
                if sid:
                    try:
                        await RedisCartRepo().clear(session_id=sid)
                    except Exception as e:
                        logger.warning('Failed to clear cart on session expiry: %s', e)
                session.clear()
        return await call_next(request)
