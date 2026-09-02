import asyncio

import fakeredis
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.api.routes import router
from app.domain.models import Base, MediaPost, PostStatus
from app.middleware import IdempotencyMiddleware


@pytest.fixture
def test_app(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    fake_redis = fakeredis.FakeStrictRedis(decode_responses=True)
    delayed_posts = []

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.add_middleware(IdempotencyMiddleware)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db

    from app.api import routes
    from app.middleware import idempotency

    monkeypatch.setattr(idempotency, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(routes.process_media, "delay", lambda post_id: delayed_posts.append(post_id))

    return app, fake_redis, TestingSessionLocal, delayed_posts


@pytest_asyncio.fixture
async def async_client(test_app):
    app, _, _, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_publish_accepts_new_idempotency_key(async_client, test_app):
    _, fake_redis, _, delayed_posts = test_app
    key = "key-new"

    response = await async_client.post(
        "/api/v1/publish",
        headers={"X-Idempotency-Key": key},
        json={"media_url": "https://example.com/1.jpg", "caption": "first"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["id"] == key
    assert payload["media_url"] == "https://example.com/1.jpg"
    assert payload["status"] == "MEDIA_UPLOADED"
    assert delayed_posts == [key]
    assert fake_redis.get(f"idempotency_response:{key}") is not None


@pytest.mark.asyncio
async def test_duplicate_request_with_same_key_returns_cached_response(async_client):
    key = "dup-key"
    body = {"media_url": "https://example.com/dup.jpg", "caption": "dup"}

    first = await async_client.post("/api/v1/publish", headers={"X-Idempotency-Key": key}, json=body)
    second = await async_client.post("/api/v1/publish", headers={"X-Idempotency-Key": key}, json=body)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json() == first.json()


@pytest.mark.asyncio
async def test_payload_mismatch_for_same_key_returns_422(async_client):
    key = "mismatch-key"
    first_body = {"media_url": "https://example.com/a.jpg", "caption": "same"}
    second_body = {"media_url": "https://example.com/b.jpg", "caption": "same"}

    first = await async_client.post("/api/v1/publish", headers={"X-Idempotency-Key": key}, json=first_body)
    second = await async_client.post("/api/v1/publish", headers={"X-Idempotency-Key": key}, json=second_body)

    assert first.status_code == 202
    assert second.status_code == 422
    assert "Payload mismatch" in second.json()["detail"]


@pytest.mark.asyncio
async def test_concurrent_requests_wait_and_receive_cached_response(async_client, test_app):
    _, _, SessionLocal, _ = test_app
    key = "race-key"
    body = {"media_url": "https://example.com/race.jpg", "caption": "race"}

    async def send_request():
        return await async_client.post(
            "/api/v1/publish", headers={"X-Idempotency-Key": key}, json=body
        )

    responses = await asyncio.gather(*[send_request() for _ in range(6)])
    status_codes = [response.status_code for response in responses]

    assert status_codes.count(202) == 6
    first_body = responses[0].json()
    for response in responses[1:]:
        assert response.json() == first_body

    with SessionLocal() as db:
        posts = db.query(MediaPost).filter(MediaPost.id == key).all()
        assert len(posts) == 1


@pytest.mark.asyncio
async def test_requests_without_idempotency_key_pass_through(async_client):
    body = {"media_url": "https://example.com/no-header.jpg", "caption": "none"}
    first = await async_client.post("/api/v1/publish", json=body)
    second = await async_client.post("/api/v1/publish", json=body)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.asyncio
async def test_patch_post_respects_state_machine(async_client, test_app):
    _, _, SessionLocal, _ = test_app
    create = await async_client.post("/api/v1/publish", json={"caption": "draft"})
    post_id = create.json()["id"]
    assert create.json()["status"] == "DRAFT"

    caption_only = await async_client.patch(
        f"/api/v1/posts/{post_id}",
        json={"caption": "updated draft"},
    )
    assert caption_only.status_code == 200
    assert caption_only.json()["status"] == "DRAFT"

    media_update = await async_client.patch(
        f"/api/v1/posts/{post_id}",
        json={"media_url": "https://example.com/new.jpg"},
    )
    assert media_update.status_code == 200
    assert media_update.json()["status"] == "MEDIA_UPLOADED"

    with SessionLocal() as db:
        post = db.query(MediaPost).filter(MediaPost.id == post_id).first()
        post.status = PostStatus.PUBLISHED
        db.commit()

    published_update = await async_client.patch(
        f"/api/v1/posts/{post_id}",
        json={"caption": "cannot edit"},
    )
    assert published_update.status_code == 409
