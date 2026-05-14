import os
import redis

_client = None

def get_redis():
    global _client
    if _client is None:
        _client = redis.from_url(os.getenv('REDIS_URL', 'redis://redis:6379'))
    return _client