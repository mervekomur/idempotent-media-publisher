from pydantic import BaseModel, ConfigDict
from datetime import datetime
from app.domain.models import PostStatus

class PostCreate(BaseModel):
    media_url: str
    caption: str | None = None

class PostResponse(BaseModel):
    id: str
    media_url: str
    caption: str | None
    status: PostStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)