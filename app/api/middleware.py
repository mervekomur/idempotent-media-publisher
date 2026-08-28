from fastapi import Header, HTTPException
from app.infrastructure.cache import get_redis
from app.core.config import settings

async def verify_idempotency_key(
    x_idempotency_key: str = Header(..., description="Unique transaction key (UUID)")
):
    redis_client = get_redis()
    
    # Attempt to acquire a lock using Redis SETNX (Set if Not eXists)
    # nx=True: Only set the key if it does not already exist
    # ex=... : Automatically expire the lock after the specified duration
    is_locked = redis_client.set(
        name=f"idempotency_lock:{x_idempotency_key}", 
        value="processing", 
        nx=True, 
        ex=settings.LOCK_TIMEOUT_SECONDS
    )
    
    if not is_locked:
        # If the lock cannot be acquired, the key already exists in Redis
        raise HTTPException(
            status_code=409, 
            detail="Conflict: This request is currently being processed or has already been completed."
        )
    
    return x_idempotency_key