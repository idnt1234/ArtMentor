# ArtMentor account system

ArtMentor uses Supabase Auth for email/password identity and keeps all application
records and private artwork scoped to the verified account. The homepage,
public-domain samples, sign-up, sign-in, and password recovery remain public;
uploads, AI actions, private media, and critique history require sign-in when
`REQUIRE_ACCOUNT_FOR_WORK=true`.

## Identity flow

1. FastAPI gives each browser an opaque anonymous HttpOnly cookie. It exists only
   to support the staged access-code deployment and to claim work made before the
   public account requirement was enabled.
2. React uses the public Supabase URL and publishable key for sign-up, email
   confirmation, sign-in, refresh, sign-out, and password recovery.
3. `/api/session` sends the Supabase access token. FastAPI verifies it with the
   Supabase Auth `/user` endpoint and derives `auth:<user UUID>` as the owner ID;
   an unverified JWT payload is never trusted.
4. On the first verified session, any projects owned by that browser's old
   anonymous digest are moved to the account in one database transaction.
5. FastAPI issues a seven-day HMAC-signed HttpOnly bridge containing only the
   user UUID, optional email, and expiry. This lets private image requests and
   routine API calls enforce ownership without putting a token in an image URL.
6. Logout clears the bridge before the browser removes the Supabase session.

Analyses, feedback, revisions, pose records, and private media inherit ownership
through their project. Daily AI usage is stored separately by Supabase user UUID
and UTC date.

## Configuration

```text
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
SUPABASE_SECRET_KEY=sb_secret_...
REQUIRE_ACCOUNT_FOR_WORK=true
ACCOUNT_DAILY_AI_LIMIT=5
ACCOUNT_COOKIE_MAX_AGE=604800
```

The publishable key is intentionally sent to the browser. `SUPABASE_SECRET_KEY`
must exist only in the FastAPI/Render environment; it is used for the confirmed
self-service deletion endpoint. If the secret is absent, deletion fails closed
before any records are removed. Never put a secret/service-role key in a
`VITE_` variable or frontend source.

`ACCOUNT_DAILY_AI_LIMIT` counts paid AI actions (intent context check, critique,
and revision comparison) per account per UTC day. Set it to `0` only when an
unlimited deployment is intentional. IP-based upload and AI sliding-window
limits remain an additional abuse-control layer.

## Supabase dashboard checklist

- Enable Email sign-ups and Confirm Email.
- Set Site URL to the production HTTPS origin and allow that exact origin plus
  `http://localhost:5173/**` in Redirect URLs.
- Configure a custom SMTP provider before removing the access code. Add the
  provider's SPF and DKIM records, and publish DMARC for the sending domain.
- Review Supabase Auth rate limits. Enable CAPTCHA before broad public promotion
  if automated sign-ups become a concern; account registration goes directly
  from the browser to Supabase, so the FastAPI upload limiter does not cover it.

## Account lifecycle and privacy

The account dialog shows the remaining UTC-day allowance and provides:

- a ZIP export containing `account.json` plus original, revision, and pose
  reference images;
- permanent deletion of private objects, application rows, daily counters, and
  the Supabase Auth identity after the user types `DELETE` and supplies a fresh
  verified access token;
- normal sign-out without deleting stored data.

The public notice states what is stored and when content is sent to the configured
AI provider. Product copy must not imply that an uploaded image stays solely on
ArtMentor infrastructure after the user requests an AI action.

## Verification

Offline tests cover rejected Auth responses, signed-cookie tampering, public vs.
private endpoint boundaries, account isolation, durable daily quota exhaustion,
ZIP export, recent-token deletion, object/data cleanup, and server-secret Auth
deletion. Frontend verification includes TypeScript, ESLint, and a production
Vite build.
