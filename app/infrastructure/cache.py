import redis.asyncio as redis
from app.core.config import settings

# Isolate the Redis connection from the rest of the application (Singleton Pattern)
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    decode_responses=True
)

def get_redis():
    return redis_client