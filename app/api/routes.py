from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.api.middleware import verify_idempotency_key
from app.api.dependencies import get_db
from app.domain import schemas, models
from app.services.worker import process_media  # İşçimizi içeri alıyoruz

router = APIRouter()

@router.post("/publish", response_model=schemas.PostResponse, status_code=status.HTTP_202_ACCEPTED)
async def publish_media(
    post_data: schemas.PostCreate,
    idempotency_key: str = Depends(verify_idempotency_key),
    db: Session = Depends(get_db)
):
    # 1. Create the database record (State: PENDING)
    new_post = models.MediaPost(
        id=idempotency_key,
        media_url=post_data.media_url,
        caption=post_data.caption
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    # 2. Dispatch task to Celery Worker (Asenkron tetikleme)
    process_media.delay(new_post.id)

    # 3. Return immediate 202 Accepted response (Non-blocking)
    return new_post