# Deploy ArtMentor with Render and Supabase

This production path keeps the public application in one Render Docker web service. FastAPI serves both the built React site and `/api`; Supabase provides durable PostgreSQL and private S3-compatible artwork storage.

## 1. Create the Supabase resources

1. Create a Supabase project in a nearby region.
2. In Storage, create a **private** bucket named `artmentor-artworks`.
3. In the project connection settings, copy the PostgreSQL connection string. Prefer the session pooler when the direct database endpoint is not reachable over IPv4. Keep `sslmode=require` in the URL.
4. In Storage S3 settings, create an S3 access key and note the endpoint, region, access key ID, and secret access key.

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
| `GPTSAPI_KEY` | WildAI / GPTsAPI key |
| `DEMO_ACCESS_CODE` | A code shared only with reviewers and testers |

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
| `SESSION_COOKIE_SECURE` | `true` |
| `MAX_UPLOAD_MB` | `10` |
| `ANALYSIS_MAX_SIDE` | `1600` |
| `AI_RATE_LIMIT_PER_HOUR` | `12` |
| `UPLOAD_RATE_LIMIT_PER_HOUR` | `8` |
| `MAX_CONCURRENT_AI_REQUESTS` | `1` |

The access code is optional in code, but required by this Blueprint prompt and strongly recommended because every successful critique spends a shared third-party API allowance.

## 5. Verify the deployed result

After Render reports **Live**:

1. Open `/api/health` and confirm `status` is `ok`, `storage` is `s3`, and `ai_configured` is `true`.
2. Open the root URL in a private browser window and confirm the access gate appears.
3. Import one public-domain sample, run a critique, refresh the page, and confirm it remains in Recent work.
4. Open a second private browser profile and confirm the first profile's project is not listed and its media URL returns 404.
5. Upload a revision and confirm the before/after report survives a Render restart.

## Privacy and operational limits

- The anonymous HttpOnly cookie separates visitors without collecting an email or username.
- Clearing that cookie makes the old history inaccessible to that browser; it does not delete the stored data. Account login and self-service deletion belong in the next version.
- Uploaded images are private application objects, but they are sent to the configured vision provider for the requested visual context check and again for the confirmed critique.
- Rate limits are in memory and reset when the service restarts. The access code is the main cost-control boundary for this MVP.
- Render's local filesystem is not used for production data, so sleep or rebuild does not remove Supabase records or images.
- A free Render service sleeps after 15 minutes without inbound traffic. Its first request after sleep can take about a minute while the container starts.
