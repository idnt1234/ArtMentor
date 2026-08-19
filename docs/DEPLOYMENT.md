# Deploy ArtMentor with Render and Supabase

This production path keeps the public application in one Render Docker web service. FastAPI serves both the built React site and `/api`; Supabase provides durable PostgreSQL and private S3-compatible artwork storage.

## 1. Create the Supabase resources

1. Create a Supabase project in a nearby region.
2. In Storage, create a **private** bucket named `artmentor-artworks`.
3. In the project connection settings, copy the PostgreSQL connection string. Prefer the session pooler when the direct database endpoint is not reachable over IPv4. Keep `sslmode=require` in the URL.
4. In Storage S3 settings, create an S3 access key and note the endpoint, region, access key ID, and secret access key.
5. In Authentication providers, keep Email enabled, allow new sign-ups, and keep Confirm Email enabled.
6. In Authentication URL Configuration, set Site URL to the exact Render HTTPS origin. Add that same origin and `http://localhost:5173/**` to Redirect URLs.
7. In Project Settings → API Keys, create/copy a server secret key for the deletion endpoint. Do not use this key in the browser.

Do not commit any copied value. ArtMentor accepts Supabase's normal `postgresql://...` URL and switches it to the installed psycopg 3 driver internally.

## 2. Publish the repository

Push this repository to a public GitHub repository. The root Dockerfile builds the React frontend, installs the FastAPI backend, then serves both from one process. Never commit `.env` or any value from the tables below.

## 3. Create the Render Blueprint

1. Sign in to Render and choose **New → Blueprint**.
2. Connect the public GitHub repository.
3. Render detects `render.yaml`, creates a free Docker web service, and prompts for every entry marked `sync: false`.
4. Keep the generated `SESSION_SECRET`; do not replace it with a value committed to source control.

The Blueprint includes the health check, Supabase endpoint and region, free instance plan, upload limits, AI-call limits, and automatic deploys from the default branch.

## 4. Enter deployment secrets

Enter these only in Render's Blueprint secret prompts:

| Secret | Value |
| --- | --- |
| `DATABASE_URL` | Supabase PostgreSQL connection string, including `sslmode=require` |
| `S3_ACCESS_KEY` | Supabase Storage S3 access key ID |
| `S3_SECRET_KEY` | Supabase Storage S3 secret access key |
| `SUPABASE_PUBLISHABLE_KEY` | Supabase project's browser-safe publishable key (`sb_publishable_...`); never use a secret/service-role key |
| `SUPABASE_SECRET_KEY` | Supabase server secret (`sb_secret_...`) used only for confirmed self-service Auth deletion; never expose it to the frontend |
| `GPTSAPI_KEY` | WildAI / GPTsAPI key |
| `DEMO_ACCESS_CODE` | A code shared only with reviewers and testers |
| `POSE_WORKER_URL` | Private GPU worker HTTPS base address, without `/health` |
| `POSE_WORKER_TOKEN` | Same private Bearer token stored on the GPU worker |

The checked-in `render.yaml` supplies these non-secret variables:

| Variable | Recommended value |
| --- | --- |
| `AI_PROVIDER` | `gptsapi` |
| `GPTSAPI_BASE_URL` | `https://api.gptsapi.net/v1` |
| `GPTSAPI_MODEL` | `gpt-5.6-terra` |
| `ALLOW_DEMO_FALLBACK` | `false` |
| `STORAGE_BACKEND` | `s3` |
| `S3_ENDPOINT` | Supabase Storage S3 endpoint |
| `S3_BUCKET` | `artmentor-artworks` |
| `S3_REGION` | Region shown in the Supabase S3 settings |
| `S3_AUTO_CREATE_BUCKET` | `false` |
| `SUPABASE_URL` | Supabase project URL, supplied by the Blueprint for the current project |
| `SESSION_COOKIE_SECURE` | `true` |
| `ACCOUNT_COOKIE_MAX_AGE` | `604800` (seven days) |
| `REQUIRE_ACCOUNT_FOR_WORK` | `true` |
| `ACCOUNT_DAILY_AI_LIMIT` | `5` paid AI actions per account per UTC day |
| `MAX_UPLOAD_MB` | `10` |
| `ANALYSIS_MAX_SIDE` | `1600` |
| `AI_RATE_LIMIT_PER_HOUR` | `12` |
| `UPLOAD_RATE_LIMIT_PER_HOUR` | `8` |
| `MAX_CONCURRENT_AI_REQUESTS` | `1` |
| `POSE_FEATURE_ENABLED` | Keep `false` until the GPU URL/token are both set and tested |
| `POSE_PROVIDER` | `worker` |
| `POSE_WORKER_TIMEOUT_SECONDS` | `45` |

Keep the access code during staged validation. After all public-mode checks pass,
clear `DEMO_ACCESS_CODE` in Render and redeploy. The homepage, public samples, and
account screens then become public, while uploads, project history, private media,
and AI actions still require a verified account. Cost protection comes from both
the durable account-day allowance and the existing IP sliding-window limits.

### Enable account email delivery

Supabase's built-in mail service is for initial testing, not public production:
delivery is restricted and its quota is very low. Before clearing the access code:

1. Create an account with a transactional email provider and verify a sending
   domain or subdomain.
2. Add the provider's SPF and DKIM DNS records, and publish a DMARC policy for
   that sending domain.
3. In Supabase Authentication → SMTP Settings, enable custom SMTP and enter the
   provider's host, port, username, password, sender address, and sender name.
4. Send confirmation and password-reset messages to at least two unrelated mail
   providers, follow the links, and verify that both return to the production site.
5. Review Supabase Auth email and sign-up rate limits. Enable CAPTCHA before broad
   promotion if automated registrations are a concern.

SMTP credentials belong only in the Supabase dashboard. They are not Render
variables and must never be committed to this repository.

The browser receives only `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`. S3
credentials, database credentials, Supabase secret/service-role keys, and JWT
signing secrets must never be placed in either frontend code or that variable.

### Enable the separate 2D pose worker

The web image never includes Torch, MMPose or model weights. After the private
GPU endpoint passes both `/health` and an authenticated real-image smoke test:

1. Enter `POSE_WORKER_URL` and `POSE_WORKER_TOKEN` in the Render service's
   environment settings. Never prefix these with `VITE_`; they must remain
   server-only.
2. Set `POSE_FEATURE_ENABLED=true` and redeploy.
3. Confirm `/api/session` returns `pose_enabled: true`; the frontend will then
   reveal the Body structure tab. When the flag is false, the tab stays hidden
   rather than opening a feature that must fail.
4. Keep the Render demo protected by `DEMO_ACCESS_CODE` while the GPU endpoint
   is authorized only for private testing.

Turning the GPU instance off makes new skeleton estimation unavailable. It does
not affect the normal critique flow or already saved, user-corrected skeletons.

## 5. Verify the deployed result

After Render reports **Live**:

1. Open `/api/health` and confirm `status` is `ok`, `storage` is `s3`, and `ai_configured` is `true`.
2. While `DEMO_ACCESS_CODE` is set, open the root URL in a private browser window and confirm the access gate appears.
3. Sign in, import one public-domain sample, run a critique, refresh the page, and confirm it remains in Recent work.
4. Sign out and confirm project history, upload, sample import, AI APIs, and private media are unavailable, while `/api/session`, `/api/samples`, sign-up, and sign-in remain available.
5. Upload a revision and confirm the before/after report survives a Render restart.
6. When pose is enabled, estimate one artwork skeleton, correct a point, save it,
   run the 2D check, refresh the page, and confirm the corrected skeleton remains.
7. Download the account export and inspect `account.json` plus the included image folders.
8. In a disposable account, type `DELETE`, permanently delete it, and confirm the old credentials no longer sign in and its media URL no longer resolves.
9. Exhaust the configured daily allowance in a test account and confirm the next AI action returns `429` while upload/history access still works.
10. Request a password reset and confirm the custom-SMTP email returns to the Render site with the new-password dialog.
11. Clear `DEMO_ACCESS_CODE`, redeploy, and repeat steps 3–10 from a clean profile before announcing the public URL.

## Privacy and operational limits

- Public browsing does not grant a private workspace. With `REQUIRE_ACCOUNT_FOR_WORK=true`, project and media APIs require a verified account even after the access code is removed.
- A verified account can still claim old browser history created before the public account requirement was enabled.
- Self-service ZIP export and permanent account/data deletion are available in the account dialog. Deletion requires `SUPABASE_SECRET_KEY` on the server and a fresh verified user token.
- Uploaded images are private application objects, but they are sent to the configured vision provider for the requested visual context check and again for the confirmed critique.
- Per-account daily AI usage is durable in PostgreSQL. IP upload/AI windows remain in memory and reset with the web process; Supabase separately enforces Auth endpoint limits.
- Render's local filesystem is not used for production data, so sleep or rebuild does not remove Supabase records or images.
- A free Render service sleeps after 15 minutes without inbound traffic. Its first request after sleep can take about a minute while the container starts.
