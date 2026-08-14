import base64
import binascii
from dataclasses import dataclass
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
ACCOUNT_COOKIE = "artmentor_account"


@dataclass(frozen=True)
class AccountCookie:
    user_id: str
    email: str | None = None


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


def account_owner_id(user_id: str) -> str:
    """把 Supabase 用户 UUID 放入现有 owner_id 命名空间，避免与匿名摘要混淆。"""
    return f"auth:{uuid.UUID(user_id)}"


def signed_account_cookie(
    user_id: str,
    secret: str,
    max_age: int,
    email: str | None = None,
) -> str:
    """签发账户桥接 Cookie，供刷新后的页面和私有媒体继续鉴权。"""
    normalized = str(uuid.UUID(user_id))
    expires_at = int(time.time()) + max(1, max_age)
    encoded_email = (
        base64.urlsafe_b64encode(email.encode("utf-8")).decode("ascii").rstrip("=")
        if email
        else ""
    )
    payload = f"{normalized}.{expires_at}.{encoded_email}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def valid_account_cookie(value: str | None, secret: str) -> AccountCookie | None:
    """验证账户桥接 Cookie 的签名和时效，返回可信账户资料。"""
    if not value:
        return None
    try:
        parts = value.split(".")
        if len(parts) == 3:
            # Accept the first-release cookie until its one-hour lifetime ends.
            user_id, expires_raw, signature = parts
            encoded_email = ""
            payload = f"{user_id}.{expires_raw}"
        elif len(parts) == 4:
            user_id, expires_raw, encoded_email, signature = parts
            payload = f"{user_id}.{expires_raw}.{encoded_email}"
        else:
            return None
        normalized = str(uuid.UUID(user_id))
        expires_at = int(expires_raw)
        email = None
        if encoded_email:
            padding = "=" * (-len(encoded_email) % 4)
            email = base64.urlsafe_b64decode(encoded_email + padding).decode("utf-8")
            if len(email) > 320:
                return None
    except (ValueError, TypeError, UnicodeDecodeError, binascii.Error):
        return None
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected) or expires_at < int(time.time()):
        return None
    return AccountCookie(user_id=normalized, email=email)


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
