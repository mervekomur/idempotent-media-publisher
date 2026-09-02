from fastapi import FastAPI
from app.core.config import settings
from app.api.routes import router
from app.domain.models import Base
from app.infrastructure.database import engine
from app.middleware import IdempotencyMiddleware

# Automatically create database tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION)
app.add_middleware(IdempotencyMiddleware)

# Register the routes
app.include_router(router, prefix="/api/v1")