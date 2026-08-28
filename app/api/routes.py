from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.api.middleware import verify_idempotency_key
from app.api.dependencies import get_db
from app.domain import schemas, models
from app.services.worker import process_media

router = APIRouter()

@router.post("/publish", response_model=schemas.PostResponse, status_code=status.HTTP_202_ACCEPTED)
async def publish_media(
    post_data: schemas.PostCreate,
    idempotency_key: str = Depends(verify_idempotency_key),
    db: Session = Depends(get_db)
):
    try:
        new_post = models.MediaPost(
            id=idempotency_key,
            media_url=post_data.media_url,
            caption=post_data.caption
        )
        db.add(new_post)
        db.commit()
        db.refresh(new_post)
        
        process_media.delay(new_post.id)
        return new_post
        
    except IntegrityError:
        db.rollback()
        # Sistemde kayıtlı ise, çökme yaşatmadan mevcut durumu döndür
        existing_post = db.query(models.MediaPost).filter(models.MediaPost.id == idempotency_key).first()
        if existing_post:
            return existing_post
        raise HTTPException(status_code=409, detail="Transaction conflict.")