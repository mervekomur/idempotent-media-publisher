from fastapi import APIRouter, Depends, status, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.api.dependencies import get_db
from app.domain import schemas, models
from app.services.worker import process_media

router = APIRouter()

@router.post("/publish", response_model=schemas.PostResponse, status_code=status.HTTP_202_ACCEPTED)
async def publish_media(
    request: Request,
    post_data: schemas.PostCreate,
    db: Session = Depends(get_db)
):
    idempotency_key = request.state.idempotency_key
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