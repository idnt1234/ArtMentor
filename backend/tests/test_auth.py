import asyncio
import hashlib
import hmac
import time

import httpx
import pytest

from app.auth import AuthServiceUnavailable, InvalidAuthToken, SupabaseAuthVerifier
from app.config import Settings
from app.security import signed_account_cookie, valid_account_cookie


def verifier_with(handler: httpx.MockTransport) -> SupabaseAuthVerifier:
    settings = Settings(
        supabase_url="https://project.supabase.co",
        supabase_publishable_key="sb_publishable_test",
    )
    verifier = SupabaseAuthVerifier(settings)
    original = verifier._client
    verifier._client = httpx.AsyncClient(
        transport=handler, base_url="https://project.supabase.co"
    )
    if original is not None:
        asyncio.run(original.aclose())
    return verifier


def test_supabase_verifier_accepts_only_auth_server_user_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/auth/v1/user"
        assert request.headers["apikey"] == "sb_publishable_test"
        assert request.headers["authorization"] == "Bearer verified-token"
        return httpx.Response(
            200,
            json={
                "id": "11111111-1111-4111-8111-111111111111",
                "email": "artist@example.com",
            },
        )

    verifier = verifier_with(httpx.MockTransport(handler))
    try:
        user = asyncio.run(verifier.verify("verified-token"))
        assert user.id == "11111111-1111-4111-8111-111111111111"
        assert user.email == "artist@example.com"
    finally:
        asyncio.run(verifier.close())


def test_supabase_verifier_fails_closed_for_rejection_or_invalid_identity() -> None:
    rejected = verifier_with(
        httpx.MockTransport(lambda _request: httpx.Response(401, json={"message": "bad"}))
    )
    try:
        with pytest.raises(InvalidAuthToken):
            asyncio.run(rejected.verify("expired"))
    finally:
        asyncio.run(rejected.close())

    malformed = verifier_with(
        httpx.MockTransport(lambda _request: httpx.Response(200, json={"id": "not-a-uuid"}))
    )
    try:
        with pytest.raises(AuthServiceUnavailable):
            asyncio.run(malformed.verify("malformed"))
    finally:
        asyncio.run(malformed.close())


def test_account_bridge_cookie_rejects_tampering() -> None:
    user_id = "11111111-1111-4111-8111-111111111111"
    cookie = signed_account_cookie(user_id, "test-secret", 60, "artist@example.com")
    parsed = valid_account_cookie(cookie, "test-secret")
    assert parsed is not None
    assert parsed.user_id == user_id
    assert parsed.email == "artist@example.com"
    assert valid_account_cookie(f"{cookie[:-1]}0", "test-secret") is None
    assert valid_account_cookie(cookie, "different-secret") is None


def test_account_bridge_cookie_accepts_first_release_format() -> None:
    user_id = "11111111-1111-4111-8111-111111111111"
    expires_at = int(time.time()) + 60
    payload = f"{user_id}.{expires_at}"
    signature = hmac.new(b"test-secret", payload.encode(), hashlib.sha256).hexdigest()
    parsed = valid_account_cookie(f"{payload}.{signature}", "test-secret")
    assert parsed is not None
    assert parsed.user_id == user_id
    assert parsed.email is None
