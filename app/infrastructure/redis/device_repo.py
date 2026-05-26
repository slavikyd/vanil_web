import logging
import random

from app.redis import redis

logger = logging.getLogger(__name__)

DEVICE_CODE_TTL = 600


class DeviceRepo:
    def _key(self, code: str) -> str:
        return f'device_reg:{code}'

    async def create_code(self, *, android_id: str) -> str:
        code = f'{random.randint(0, 999999):06d}'
        try:
            await redis.set(self._key(code), android_id, ex=DEVICE_CODE_TTL)
        except Exception as e:
            logger.warning('failed to store device code', extra={'error': str(e)})
        return code

    async def consume_code(self, *, code: str) -> str | None:
        key = self._key(code)
        try:
            android_id = await redis.get(key)
            if android_id:
                await redis.delete(key)
                return android_id
        except Exception as e:
            logger.warning('failed to consume device code', extra={'error': str(e)})
        return None