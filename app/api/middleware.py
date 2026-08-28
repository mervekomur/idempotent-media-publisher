from fastapi import Header, HTTPException
from app.infrastructure.cache import get_redis
from app.core.config import settings

async def verify_idempotency_key(
    x_idempotency_key: str = Header(..., description="Eşsiz işlem anahtarı (UUID)")
):
    redis_client = get_redis()
    
    # Redis SETNX (Set if Not eXists) komutu ile kilitleme denemesi
    # nx=True: Sadece daha önce yoksa oluştur
    # ex=... : Belirlenen süre sonra kilidi otomatik yok et
    is_locked = redis_client.set(
        name=f"idempotency_lock:{x_idempotency_key}", 
        value="processing", 
        nx=True, 
        ex=settings.LOCK_TIMEOUT_SECONDS
    )
    
    if not is_locked:
        # Eğer kilit alınamadıysa (yani anahtar zaten Redis'te varsa)
        raise HTTPException(
            status_code=409, 
            detail="Conflict: Bu işlem şu anda yürütülüyor veya daha önce tamamlandı."
        )
    
    return x_idempotency_key