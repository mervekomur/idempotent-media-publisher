import asyncio
import base64
import hashlib
import json
import uuid
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.infrastructure.cache import get_redis


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        idempotency_key = request.headers.get(settings.IDEMPOTENCY_KEY_HEADER)
        request.state.idempotency_key = idempotency_key or str(uuid.uuid4())

        if not idempotency_key:
            return await call_next(request)

        body = await request.body()
        request._body = body

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive
        payload_hash = self._compute_payload_hash(body, request.headers.get("content-type", ""))
        request.state.payload_hash = payload_hash

        redis_client = get_redis()
        lock_key = f"idempotency:lock:{idempotency_key}"
        result_key = f"idempotency:result:{idempotency_key}"
        lock_value = str(uuid.uuid4())
        lock_timeout_ms = settings.LOCK_TIMEOUT_SECONDS * 1000

        existing_result = await redis_client.hgetall(result_key)
        if existing_result:
            stored_hash = existing_result.get("payload_hash")
            if stored_hash and stored_hash != payload_hash:
                return JSONResponse(
                    status_code=409,
                    content={"detail": "Idempotency key reuse with different payload is not allowed."},
                )
            if existing_result.get("status") == "completed":
                return self._build_cached_response(existing_result)

        is_locked = await redis_client.set(lock_key, lock_value, nx=True, px=lock_timeout_ms)
        if is_locked:
            await redis_client.hset(
                result_key,
                mapping={
                    "status": "processing",
                    "payload_hash": payload_hash,
                },
            )
            await redis_client.expire(result_key, settings.IDEMPOTENCY_RESULT_TTL_SECONDS)
            try:
                response = await call_next(request)
                return await self._store_and_return_response(redis_client, result_key, payload_hash, response)
            except Exception:
                await redis_client.delete(result_key)
                raise
            finally:
                if await redis_client.get(lock_key) == lock_value:
                    await redis_client.delete(lock_key)

        return await self._wait_and_return_response(
            redis_client=redis_client,
            lock_key=lock_key,
            result_key=result_key,
            payload_hash=payload_hash,
        )

    async def _store_and_return_response(self, redis_client, result_key: str, payload_hash: str, response: Response) -> Response:
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        headers = dict(response.headers)
        encoded_body = base64.b64encode(body).decode("ascii")
        await redis_client.hset(
            result_key,
            mapping={
                "status": "completed",
                "payload_hash": payload_hash,
                "response_status_code": str(response.status_code),
                "response_media_type": response.media_type or "",
                "response_headers": json.dumps(headers, sort_keys=True),
                "response_body": encoded_body,
            },
        )
        await redis_client.expire(result_key, settings.IDEMPOTENCY_RESULT_TTL_SECONDS)

        filtered_headers = {k: v for k, v in headers.items() if k.lower() != "content-length"}
        return Response(
            content=body,
            status_code=response.status_code,
            headers=filtered_headers,
            media_type=response.media_type,
        )

    async def _wait_and_return_response(self, redis_client, lock_key: str, result_key: str, payload_hash: str) -> Response:
        timeout = settings.IDEMPOTENCY_WAIT_TIMEOUT_SECONDS
        elapsed = 0.0
        while elapsed < timeout:
            data = await redis_client.hgetall(result_key)
            if data:
                stored_hash = data.get("payload_hash")
                if stored_hash and stored_hash != payload_hash:
                    return JSONResponse(
                        status_code=409,
                        content={"detail": "Idempotency key reuse with different payload is not allowed."},
                    )

                if data.get("status") == "completed":
                    return self._build_cached_response(data)

            if not await redis_client.exists(lock_key):
                break

            await asyncio.sleep(settings.IDEMPOTENCY_POLL_INTERVAL_SECONDS)
            elapsed += settings.IDEMPOTENCY_POLL_INTERVAL_SECONDS

        return JSONResponse(
            status_code=409,
            content={"detail": "Conflict: This request is currently being processed."},
        )

    def _build_cached_response(self, data: dict[str, str]) -> Response:
        status_code = int(data.get("response_status_code", "200"))
        body = base64.b64decode(data.get("response_body", ""))
        headers = json.loads(data.get("response_headers", "{}"))
        media_type = data.get("response_media_type") or None
        filtered_headers = {k: v for k, v in headers.items() if k.lower() != "content-length"}
        return Response(
            content=body,
            status_code=status_code,
            headers=filtered_headers,
            media_type=media_type,
        )

    def _compute_payload_hash(self, body: bytes, content_type: str) -> str:
        caption = ""
        image_bytes = b""

        if "multipart/form-data" in content_type and "boundary=" in content_type:
            boundary = content_type.split("boundary=", 1)[1].strip().strip('"')
            caption, image_bytes = self._extract_multipart_parts(body, boundary)
        else:
            try:
                payload = json.loads(body.decode("utf-8")) if body else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = {}

            raw_caption = payload.get("caption")
            caption = raw_caption if isinstance(raw_caption, str) else ""

            image_payload = payload.get("image", "")
            if image_payload is None:
                image_payload = ""
            if isinstance(image_payload, str):
                image_bytes = image_payload.encode("utf-8")
            elif isinstance(image_payload, bytes):
                image_bytes = image_payload
            else:
                image_bytes = str(image_payload).encode("utf-8")

        canonical_payload = json.dumps(
            {
                "caption": caption,
                "image_b64": base64.b64encode(image_bytes).decode("ascii"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()

    def _extract_multipart_parts(self, body: bytes, boundary: str) -> tuple[str, bytes]:
        caption = ""
        image_bytes = b""
        boundary_bytes = f"--{boundary}".encode("utf-8")

        for part in body.split(boundary_bytes):
            if not part or part in (b"--", b"--\r\n"):
                continue

            part = part.strip(b"\r\n")
            if b"\r\n\r\n" not in part:
                continue

            header_bytes, content = part.split(b"\r\n\r\n", 1)
            content = content.rstrip(b"\r\n")
            headers_text = header_bytes.decode("utf-8", errors="ignore")

            if 'name="caption"' in headers_text:
                caption = content.decode("utf-8", errors="ignore")
            elif 'name="image"' in headers_text:
                image_bytes = content

        return caption, image_bytes
