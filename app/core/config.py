from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Idempotent Media Publisher"
    VERSION: str = "1.0.0"
    
    # Redis Settings
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    
    # Database Settings
    DATABASE_URL: str = "postgresql://user:password@postgres:5432/publisher_db"
    
    # Idempotency Settings
    IDEMPOTENCY_KEY_HEADER: str = "X-Idempotency-Key"
    IDEMPOTENCY_LOCK_TIMEOUT_SECONDS: int = 60
    IDEMPOTENCY_RESPONSE_TTL_SECONDS: int = 300
    IDEMPOTENCY_WAIT_TIMEOUT_SECONDS: int = 30
    IDEMPOTENCY_WAIT_POLL_SECONDS: float = 0.05

    class Config:
        case_sensitive = True

settings = Settings()