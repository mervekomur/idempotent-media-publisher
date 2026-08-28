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
    LOCK_TIMEOUT_SECONDS: int = 60  # How long to block duplicate requests

    class Config:
        case_sensitive = True

settings = Settings()