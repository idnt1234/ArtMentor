# Private SAM 3D Body research worker

ArtMentor's 3D preview is isolated from both the Render web process and the
RTMPose worker. It loads the official gated `facebook/sam-3d-body-vith`
checkpoint once, accepts a user-confirmed COCO-17 skeleton, uses no more than
two supported keypoint prompts, and returns four PNG evidence views.

It does **not** return an anatomy verdict. The displayed projection error only
measures agreement in the original image plane; it cannot validate hidden
depth. The NRDF research checker is deliberately not part of this deployment.

## Access boundary

The normal AutoDL Custom Service agreement limits that entry point to research
and the account holder's own use. Keep this Beta restricted to your own signed-in
email. Do not add public users to `POSE3D_ALLOWED_EMAILS` while this endpoint is
hosted through that service. A public rollout needs a GPU provider/service tier
whose terms allow serving end users.

The web application fails closed in three layers:

1. `POSE3D_FEATURE_ENABLED` defaults to `false`.
2. An empty `POSE3D_ALLOWED_EMAILS` enables nobody.
3. Render and the GPU worker must share a private Bearer token.

Ordinary critique and 2D body checks remain available if the 3D server is off.

## Server installation

Start the rented GPU server and pull the same ArtMentor commit. From the
repository root run:

```bash
export ARTMENTOR_REPO="$PWD"
bash pose3d_worker/install_autodl.sh
```

The installer creates a separate Python 3.11 Conda environment and pins the
audited SAM 3D Body repository commit. If the gated checkpoint is absent, it
stops and prints the two Hugging Face commands needed to download it. Never put
the Hugging Face token in `.env`, Git, Render, or chat.

Create a long random worker token and keep it private:

```bash
export POSE3D_WORKER_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(36))')"
export ARTMENTOR_POSE3D_HOME="$HOME/ArtMentorPose"
conda run -n sam3d-body bash pose3d_worker/start.sh
```

The worker listens on port `6008` and intentionally uses one process because
each process would load another multi-gigabyte model. Configure the AutoDL
Custom Service mapping for port `6008`, but do not share that URL.

Check the service from the server:

```bash
curl -s http://127.0.0.1:6008/health
```

Expected fields include `"status":"ok"`, `"model_ready":true`, and
`"auth_ready":true`.

## Render configuration

Only after the worker is healthy, set these Render environment variables:

```text
POSE3D_FEATURE_ENABLED=true
POSE3D_ALLOWED_EMAILS=<your exact Supabase login email>
POSE3D_WORKER_URL=<private/custom-service HTTPS URL>
POSE3D_WORKER_TOKEN=<same random token>
POSE3D_WORKER_TIMEOUT_SECONDS=180
```

Redeploy Render after saving them. `/api/session` returns `pose3d_enabled: true`
only to an authenticated allowlisted account, so another account does not see
or call the Beta.

## Acceptance check

1. Sign in with the allowlisted account.
2. Open a project and `Body structure` → `Artwork self-check`.
3. Correct and confirm the 2D skeleton.
4. Select `Generate 3D preview`.
5. Verify the overlay, camera, side, and top views load.
6. Drag and save a 2D joint; the old preview must be marked stale.
7. Stop the GPU worker and retry. The page should report a controlled 503 while
   critique, history, account actions, and existing 2D results continue to work.

Stored 3D views are private media. They are included in account export and
removed during permanent account deletion.
