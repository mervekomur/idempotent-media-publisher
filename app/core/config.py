from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Idempotent Media Publisher"
    VERSION: str = "1.0.0"
    
    # Redis Ayarları
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    
    # Veritabanı Ayarları
    DATABASE_URL: str = "postgresql://user:password@postgres:5432/publisher_db"
    
    # Idempotency Ayarları
    IDEMPOTENCY_KEY_HEADER: str = "X-Idempotency-Key"
    LOCK_TIMEOUT_SECONDS: int = 60

    class Config:
        case_sensitive = True

settings = Settings()