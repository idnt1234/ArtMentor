import hashlib
import hmac
import threading
import time
import uuid
from collections import defaultdict, deque
from contextlib import contextmanager
from typing import Iterator

from fastapi import HTTPException, Request

from .config import Settings


SESSION_COOKIE = "artmentor_session"


def valid_session_token(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def owner_hash(token: str, secret: str) -> str:
    # 数据库只保存不可逆摘要，不保存浏览器 Cookie 本身。
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def request_owner(request: Request) -> str:
    owner_id = getattr(request.state, "owner_id", None)
    if not owner_id:
        raise HTTPException(500, "Anonymous session is unavailable.")
    return owner_id


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: int = 3600) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        if self.limit <= 0:
            return
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) >= self.limit:
                retry_after = max(1, int(events[0] + self.window_seconds - now))
                raise HTTPException(
                    429,
                    "This demo has reached its hourly AI limit. Please try again later.",
                    headers={"Retry-After": str(retry_after)},
                )
            events.append(now)


class AIGuard:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.limiter = SlidingWindowLimiter(settings.ai_rate_limit_per_hour)
        self.upload_limiter = SlidingWindowLimiter(settings.upload_rate_limit_per_hour)
        self.capacity = threading.BoundedSemaphore(
            max(1, settings.max_concurrent_ai_requests)
        )

    def _client_key(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for", "")
        # 反向代理会把真实客户端地址追加在末尾，避免信任用户伪造的首项。
        client_ip = forwarded.split(",")[-1].strip() if forwarded else ""
        client_ip = client_ip or (request.client.host if request.client else "unknown")
        return owner_hash(client_ip, self.settings.session_secret)

    def check_rate(self, request: Request) -> None:
        self.limiter.check(self._client_key(request))

    def check_upload(self, request: Request) -> None:
        self.upload_limiter.check(self._client_key(request))

    @contextmanager
    def slot(self) -> Iterator[None]:
        if not self.capacity.acquire(blocking=False):
            raise HTTPException(
                503,
                "ArtMentor is helping another artist right now. Please retry shortly.",
                headers={"Retry-After": "15"},
            )
        try:
            yield
        finally:
            self.capacity.release()
