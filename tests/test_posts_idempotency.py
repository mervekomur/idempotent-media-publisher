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
from app.domain.models import Base, MediaPost
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

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

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

    from app.middleware import idempotency
    from app.api import routes

    monkeypatch.setattr(idempotency, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(routes.process_media, "delay", lambda _post_id: None)

    return app, fake_redis, TestingSessionLocal


@pytest_asyncio.fixture
async def async_client(test_app):
    app, _, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_publish_accepts_new_idempotency_key(async_client, test_app):
    _, fake_redis, _ = test_app
    key = "key-new"

    response = await async_client.post(
        "/api/v1/publish",
        headers={"x-idempotency-key": key},
        json={"media_url": "https://example.com/1.jpg", "caption": "first"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["id"] == key
    assert payload["media_url"] == "https://example.com/1.jpg"
    assert payload["status"] == "PENDING"
    redis_payload = await fake_redis.hgetall(f"idempotency:result:{key}")
    assert redis_payload["status"] == "completed"
    assert "payload_hash" in redis_payload


@pytest.mark.asyncio
async def test_duplicate_request_with_same_key_returns_conflict(async_client):
    key = "dup-key"
    body = {"media_url": "https://example.com/dup.jpg", "caption": "dup"}

    first = await async_client.post("/api/v1/publish", headers={"x-idempotency-key": key}, json=body)
    second = await async_client.post("/api/v1/publish", headers={"x-idempotency-key": key}, json=body)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json() == first.json()


@pytest.mark.asyncio
async def test_duplicate_request_after_lock_loss_returns_existing_row(async_client, test_app):
    _, fake_redis, SessionLocal = test_app
    key = "db-duplicate-key"
    body = {"media_url": "https://example.com/dbdup.jpg", "caption": "dbdup"}

    first = await async_client.post("/api/v1/publish", headers={"x-idempotency-key": key}, json=body)
    assert first.status_code == 202

    await fake_redis.delete(f"idempotency:lock:{key}")

    second = await async_client.post("/api/v1/publish", headers={"x-idempotency-key": key}, json=body)
    assert second.status_code == 202
    assert second.json()["id"] == key

    with SessionLocal() as db:
        posts = db.query(MediaPost).filter(MediaPost.id == key).all()
        assert len(posts) == 1


@pytest.mark.asyncio
async def test_concurrent_requests_only_allow_one_inflight(async_client):
    key = "race-key"
    body = {"media_url": "https://example.com/race.jpg", "caption": "race"}

    async def send_request():
        return await async_client.post(
            "/api/v1/publish", headers={"x-idempotency-key": key}, json=body
        )

    responses = await asyncio.gather(*[send_request() for _ in range(6)])
    status_codes = [response.status_code for response in responses]

    assert status_codes.count(202) == 6
    assert status_codes.count(409) == 0


@pytest.mark.asyncio
async def test_missing_idempotency_header_passes_through(async_client):
    response = await async_client.post(
        "/api/v1/publish",
        json={"media_url": "https://example.com/no-header.jpg", "caption": "none"},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["media_url"] == "https://example.com/no-header.jpg"
    assert payload["id"]


@pytest.mark.asyncio
async def test_same_key_with_different_payload_hash_returns_conflict(async_client):
    key = "hash-mismatch-key"
    first = await async_client.post(
        "/api/v1/publish",
        headers={"x-idempotency-key": key},
        json={
            "media_url": "https://example.com/hash-1.jpg",
            "caption": "same caption",
            "image": "raw-image-a",
        },
    )
    second = await async_client.post(
        "/api/v1/publish",
        headers={"x-idempotency-key": key},
        json={
            "media_url": "https://example.com/hash-2.jpg",
            "caption": "same caption",
            "image": "raw-image-b",
        },
    )

    assert first.status_code == 202
    assert second.status_code == 409
    assert "different payload" in second.json()["detail"]
