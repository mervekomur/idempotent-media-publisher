from celery import Celery
import time
from app.core.config import settings
from app.infrastructure.database import SessionLocal
from app.domain.models import MediaPost, PostStatus

# Initialize Celery app
celery_app = Celery(
    "worker",
    broker=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0",
    backend=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
)

@celery_app.task(name="process_media_task")
def process_media(post_id: str):
    db = SessionLocal()
    post = None
    try:
        # 1. Fetch the post from DB
        post = db.query(MediaPost).filter(MediaPost.id == post_id).first()
        if not post:
            return {"status": "error", "message": "Post not found"}

        # 2. Simulate heavy lifting (e.g., uploading to a social media API)
        time.sleep(5)  # Simulating a 5-second network request

        # 3. Update status to PUBLISHED
        post.status = PostStatus.PUBLISHED
        db.commit()

        return {"status": "success", "post_id": post_id}
    
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()