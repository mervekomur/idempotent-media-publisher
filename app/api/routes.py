import uuid

from fastapi import APIRouter, Depends, status, HTTPException, Request
from sqlalchemy.orm import Session
from app.api.dependencies import get_db
from app.domain import schemas, models
from app.services.worker import process_media

router = APIRouter()

@router.post("/publish", response_model=schemas.PostResponse, status_code=status.HTTP_202_ACCEPTED)
async def publish_media(
    post_data: schemas.PostCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    post_id = getattr(request.state, "idempotency_key", None) or str(uuid.uuid4())

    new_post = models.MediaPost(
        id=post_id,
        media_url=post_data.media_url,
        caption=post_data.caption,
        status=models.PostStatus.MEDIA_UPLOADED if post_data.media_url else models.PostStatus.DRAFT,
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    if new_post.status == models.PostStatus.MEDIA_UPLOADED:
        process_media.delay(new_post.id)
    return new_post


@router.patch("/posts/{post_id}", response_model=schemas.PostResponse)
async def update_post(
    post_id: str,
    post_data: schemas.PostUpdate,
    db: Session = Depends(get_db),
):
    post = db.query(models.MediaPost).filter(models.MediaPost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found.")

    if post.status == models.PostStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="Published posts cannot be updated.")

    if post_data.caption is not None:
        post.caption = post_data.caption
    if post_data.media_url is not None:
        post.media_url = post_data.media_url

    post.status = models.PostStatus.MEDIA_UPLOADED if post.media_url else models.PostStatus.DRAFT
    db.commit()
    db.refresh(post)
    return post