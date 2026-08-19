"""Supabase Auth access-token verification.

The React client owns sign-up, sign-in, email confirmation, password recovery,
and token refresh.  FastAPI treats the resulting access token only as evidence:
it asks Supabase Auth for the current user and never trusts an unverified JWT
payload or receives the user's password.
"""

from dataclasses import dataclass
import uuid

import httpx

from .config import Settings


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str | None = None


class InvalidAuthToken(Exception):
    """The supplied bearer token is absent, expired, or not issued for this project."""


class AuthServiceUnavailable(Exception):
    """Supabase Auth could not be reached, so the request must fail closed."""


class AuthAdminUnavailable(Exception):
    """Server-side account administration is missing or temporarily unavailable."""


class SupabaseAuthVerifier:
    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.auth_configured
        self._publishable_key = settings.supabase_publishable_key or ""
        self._client = (
            httpx.AsyncClient(
                base_url=(settings.supabase_url or "").rstrip("/"),
                timeout=httpx.Timeout(8.0),
            )
            if self.enabled
            else None
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def verify(self, token: str) -> AuthUser:
        """Validate a Supabase JWT through the Auth user endpoint and return its subject."""
        if not self.enabled or self._client is None:
            raise AuthServiceUnavailable("Account sign-in is not configured.")
        try:
            response = await self._client.get(
                "/auth/v1/user",
                headers={
                    "apikey": self._publishable_key,
                    "Authorization": f"Bearer {token}",
                },
            )
        except httpx.RequestError as exc:
            raise AuthServiceUnavailable("Account verification is temporarily unavailable.") from exc
        if response.status_code != 200:
            raise InvalidAuthToken("Your sign-in session has expired. Please sign in again.")
        try:
            payload = response.json()
            user_id = str(uuid.UUID(str(payload["id"])))
            email = payload.get("email")
        except (KeyError, TypeError, ValueError) as exc:
            raise AuthServiceUnavailable("The account service returned an invalid response.") from exc
        # account_owner_id performs strict UUID validation before this value reaches a query.
        return AuthUser(id=user_id, email=email if isinstance(email, str) else None)


class SupabaseAuthAdmin:
    """Minimal server-only client for permanently deleting the current Auth user."""

    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.auth_admin_configured
        self._secret_key = settings.supabase_secret_key or ""
        self._client = (
            httpx.AsyncClient(
                base_url=(settings.supabase_url or "").rstrip("/"),
                timeout=httpx.Timeout(8.0),
            )
            if self.enabled
            else None
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def delete_user(self, user_id: str) -> None:
        if not self.enabled or self._client is None:
            raise AuthAdminUnavailable(
                "Account deletion is not configured. Contact the site operator."
            )
        try:
            response = await self._client.request(
                "DELETE",
                f"/auth/v1/admin/users/{uuid.UUID(user_id)}",
                headers={
                    "apikey": self._secret_key,
                    "Authorization": f"Bearer {self._secret_key}",
                },
                json={"should_soft_delete": False},
            )
        except (httpx.RequestError, ValueError) as exc:
            raise AuthAdminUnavailable(
                "Account deletion is temporarily unavailable. Please try again."
            ) from exc
        if response.status_code not in {200, 204}:
            raise AuthAdminUnavailable(
                "The account service could not delete this account. Please try again."
            )
