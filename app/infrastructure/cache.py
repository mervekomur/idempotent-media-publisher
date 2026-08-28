import redis
from app.core.config import settings

# Redis bağlantısını uygulamanın geri kalanından soyutluyoruz (Singleton Pattern)
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    decode_responses=True
)

def get_redis():
   return redis_client