# ArtMentor account system

ArtMentor keeps anonymous use and adds optional, recoverable email/password
accounts through Supabase Auth.

## Identity flow

1. FastAPI gives every browser an opaque anonymous HttpOnly cookie and stores
   only its HMAC owner digest.
2. The React client uses the public Supabase URL and publishable key for sign-up,
   email confirmation, sign-in, token refresh, and password recovery.
3. The session-exchange API call carries the Supabase access token. FastAPI
   validates it against the Supabase Auth `/user` endpoint and derives
   `auth:<user UUID>` as the owner ID. It never accepts an unverified JWT payload.
4. The first authenticated `/api/session` updates projects owned by the current
   anonymous digest to the authenticated owner in one database transaction.
5. FastAPI also returns a one-hour HMAC-signed HttpOnly account cookie. It carries
   only a user UUID and expiry, allowing subsequent workflow and private image
   requests to pass the same ownership check without exposing tokens in URLs or
   asking Supabase Auth to validate every application request. Token refresh
   events renew this bridge through the verified session exchange.
6. Logout clears the FastAPI bridge before Supabase removes the browser session.

Only `Project` stores an owner ID. Analyses, feedback, revisions, pose records,
and private media inherit ownership through their project foreign key, so the
claim operation does not need to rewrite child rows.

## Configuration

Set both values to enable accounts:

```text
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
```

If either is absent, `/api/session` reports `auth_enabled=false`, the sign-in UI
stays hidden, and the original anonymous behavior is unchanged. Never use a
secret/service-role key as the publishable key.

In Supabase Authentication settings:

- enable Email sign-ups and Confirm Email;
- set Site URL to the production HTTPS origin;
- allow the exact production origin and `http://localhost:5173/**` as redirects;
- configure custom SMTP before accepting registrations from the public.

## Current boundary

Included: sign-up, confirmation, sign-in, sign-out, password recovery/reset,
anonymous-project claiming, cross-device history, private-media enforcement, and
offline security regression tests.

Not included: Google/social login, profile fields, MFA, self-service export or
account/data deletion, administrator UI, and durable distributed rate limiting.

## Verification

The offline suite covers rejected and malformed Supabase identity responses,
tampered bridge cookies, anonymous isolation, one-time project claiming,
cross-browser restoration, other-account denial, media access, and logout. The
frontend is checked with TypeScript, ESLint, a production Vite build, and desktop
plus 390-pixel browser smoke tests for sign-in, sign-up, and password recovery.
