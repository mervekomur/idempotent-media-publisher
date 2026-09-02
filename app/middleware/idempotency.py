import asyncio
import base64
import hashlib
import json
from typing import Any

from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.infrastructure.cache import get_redis


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        idempotency_key = request.headers.get(settings.IDEMPOTENCY_KEY_HEADER)
        if not idempotency_key:
            return await call_next(request)

        payload_hash = await self._compute_payload_hash(request)
        lock_key = f"idempotency_lock:{idempotency_key}"
        response_key = f"idempotency_response:{idempotency_key}"
        redis_client = get_redis()

        lock_payload = json.dumps({"status": "in-progress", "payload_hash": payload_hash})
        lock_acquired = redis_client.set(
            lock_key,
            lock_payload,
            nx=True,
            px=settings.IDEMPOTENCY_LOCK_TIMEOUT_SECONDS * 1000,
        )

        if lock_acquired:
            request.state.idempotency_key = idempotency_key
            response = await call_next(request)
            response = await self._cache_completed_response(
                response=response,
                lock_key=lock_key,
                response_key=response_key,
                payload_hash=payload_hash,
                redis_client=redis_client,
            )
            return response

        lock_record = self._get_json(redis_client.get(lock_key))
        if lock_record.get("payload_hash") and lock_record["payload_hash"] != payload_hash:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                content={"detail": "Payload mismatch for this Idempotency-Key."},
            )

        cached = redis_client.get(response_key)
        if cached:
            return self._build_cached_response(cached)

        timeout_at = asyncio.get_running_loop().time() + settings.IDEMPOTENCY_WAIT_TIMEOUT_SECONDS
        while asyncio.get_running_loop().time() < timeout_at:
            cached = redis_client.get(response_key)
            if cached:
                return self._build_cached_response(cached)

            current_lock = self._get_json(redis_client.get(lock_key))
            if current_lock.get("payload_hash") and current_lock["payload_hash"] != payload_hash:
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    content={"detail": "Payload mismatch for this Idempotency-Key."},
                )
            await asyncio.sleep(settings.IDEMPOTENCY_WAIT_POLL_SECONDS)

        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "Timed out waiting for in-progress request to complete."},
        )

    async def _compute_payload_hash(self, request: Request) -> str:
        body = await request.body()
        caption = ""
        image_bytes = b""

        try:
            payload = json.loads(body.decode() or "{}")
            if isinstance(payload, dict):
                caption = str(payload.get("caption") or "")
                image_field = payload.get("image_bytes")
                if image_field is None:
                    image_field = payload.get("image_base64")
                if image_field is None:
                    image_field = payload.get("media_url")

                if isinstance(image_field, str):
                    try:
                        image_bytes = base64.b64decode(image_field, validate=True)
                    except Exception:
                        image_bytes = image_field.encode()
                elif image_field is None:
                    image_bytes = b""
                else:
                    image_bytes = str(image_field).encode()
            else:
                image_bytes = body
        except Exception:
            image_bytes = body

        canonical_payload = caption.encode() + b"\x00" + image_bytes
        return hashlib.sha256(canonical_payload).hexdigest()

    async def _cache_completed_response(
        self,
        response: Response,
        lock_key: str,
        response_key: str,
        payload_hash: str,
        redis_client: Any,
    ) -> Response:
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        response_headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower() != "content-length"
        }
        cached_payload = {
            "status_code": response.status_code,
            "headers": response_headers,
            "body": base64.b64encode(body).decode(),
        }

        pipeline = redis_client.pipeline()
        pipeline.set(
            lock_key,
            json.dumps({"status": "completed", "payload_hash": payload_hash}),
            ex=settings.IDEMPOTENCY_LOCK_TIMEOUT_SECONDS,
        )
        pipeline.set(
            response_key,
            json.dumps(cached_payload),
            ex=settings.IDEMPOTENCY_RESPONSE_TTL_SECONDS,
        )
        pipeline.execute()

        return Response(
            content=body,
            status_code=response.status_code,
            headers=response_headers,
            media_type=response.media_type,
        )

    def _build_cached_response(self, cached_response: str) -> Response:
        payload = self._get_json(cached_response)
        body = base64.b64decode(payload.get("body", ""))
        headers = payload.get("headers", {})
        return Response(
            content=body,
            status_code=int(payload.get("status_code", status.HTTP_200_OK)),
            headers=headers,
            media_type=headers.get("content-type"),
        )

    @staticmethod
    def _get_json(raw_value: str | None) -> dict[str, Any]:
        if not raw_value:
            return {}
        try:
            loaded = json.loads(raw_value)
            return loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            return {}
