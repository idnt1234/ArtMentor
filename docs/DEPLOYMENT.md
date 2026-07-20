# Deploy ArtMentor with Hugging Face and Supabase

This production path keeps the public application in one Hugging Face Docker Space. FastAPI serves both the built React site and `/api`; Supabase provides durable PostgreSQL and private S3-compatible artwork storage.

## 1. Create the Supabase resources

1. Create a Supabase project in a nearby region.
2. In Storage, create a **private** bucket named `artmentor-artworks`.
3. In the project connection settings, copy the PostgreSQL connection string. Prefer the session pooler when the direct database endpoint is not reachable over IPv4. Keep `sslmode=require` in the URL.
4. In Storage S3 settings, create an S3 access key and note the endpoint, region, access key ID, and secret access key.

Do not commit any copied value. ArtMentor accepts Supabase's normal `postgresql://...` URL and switches it to the installed psycopg 3 driver internally.

## 2. Create the Hugging Face Space

Create a new Space with:

- SDK: **Docker**
- Visibility: **Public**
- Port: `7860` (declared by the README metadata and root Dockerfile)

Push the repository contents to the Space repository. The root Dockerfile builds the React frontend, installs the FastAPI backend, then serves both from one process.

## 3. Configure Space secrets

Add these under **Settings → Variables and secrets → Secrets**:

| Secret | Value |
| --- | --- |
| `DATABASE_URL` | Supabase PostgreSQL connection string, including `sslmode=require` |
| `S3_ACCESS_KEY` | Supabase Storage S3 access key ID |
| `S3_SECRET_KEY` | Supabase Storage S3 secret access key |
| `GPTSAPI_KEY` | WildAI / GPTsAPI key |
| `SESSION_SECRET` | A new long random string, at least 32 characters |
| `DEMO_ACCESS_CODE` | A code shared only with reviewers and testers |

Generate `SESSION_SECRET` locally without putting it in chat or source control:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Add these as ordinary Space variables:

| Variable | Recommended value |
| --- | --- |
| `AI_PROVIDER` | `gptsapi` |
| `GPTSAPI_BASE_URL` | `https://api.gptsapi.net/v1` |
| `GPTSAPI_MODEL` | `gpt-5.6-terra` |
| `ALLOW_DEMO_FALLBACK` | `false` |
| `STORAGE_BACKEND` | `s3` |
| `S3_ENDPOINT` | Supabase Storage S3 endpoint shown in the dashboard |
| `S3_BUCKET` | `artmentor-artworks` |
| `S3_REGION` | Region shown in the Supabase S3 settings |
| `S3_AUTO_CREATE_BUCKET` | `false` |
| `SESSION_COOKIE_SECURE` | `true` |
| `MAX_UPLOAD_MB` | `10` |
| `AI_RATE_LIMIT_PER_HOUR` | `20` |
| `UPLOAD_RATE_LIMIT_PER_HOUR` | `10` |
| `MAX_CONCURRENT_AI_REQUESTS` | `2` |

The access code is optional in code, but strongly recommended because every successful critique spends a shared third-party API allowance.

## 4. Verify the deployed result

After the Space reports **Running**:

1. Open `/api/health` and confirm `status` is `ok`, `storage` is `s3`, and `ai_configured` is `true`.
2. Open the root URL in a private browser window and confirm the access gate appears.
3. Import one public-domain sample, run a critique, refresh the page, and confirm it remains in Recent work.
4. Open a second private browser profile and confirm the first profile's project is not listed and its media URL returns 404.
5. Upload a revision and confirm the before/after report survives a Space restart.

## Privacy and operational limits

- The anonymous HttpOnly cookie separates visitors without collecting an email or username.
- Clearing that cookie makes the old history inaccessible to that browser; it does not delete the stored data. Account login and self-service deletion belong in the next version.
- Uploaded images are private application objects, but they are sent to the configured vision provider when the user explicitly starts a critique.
- Rate limits are in memory and reset when the Space restarts. The access code is the main cost-control boundary for this MVP.
- Hugging Face's local filesystem is not used for production data, so Space sleep or rebuild does not remove Supabase records or images.
