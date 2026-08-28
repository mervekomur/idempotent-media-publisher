from sqlalchemy import Column, String, DateTime, Enum
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone
import enum

Base = declarative_base()

class PostStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class MediaPost(Base):
    __tablename__ = "media_posts"

    # We use the idempotency key as the primary key to guarantee uniqueness at the DB level
    id = Column(String, primary_key=True, index=True)
    
    caption = Column(String, nullable=True)
    media_url = Column(String, nullable=False)
    
    status = Column(Enum(PostStatus), default=PostStatus.PENDING, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))