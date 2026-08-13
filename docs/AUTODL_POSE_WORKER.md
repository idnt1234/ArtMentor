# AutoDL RTMPose Worker Runbook

Last checked: 2026-08-12 (Asia/Shanghai)

This runbook deploys only the 2D RTMPose worker. It does not install SAM 3D
Body, MHR, NRDF, or the Stage 3 research pipeline.

## Important AutoDL boundary

AutoDL's normal container-instance custom service exposes ports 6006/6008, but
its current supplemental agreement limits that facility to scientific research,
the account holder's own use, and no forwarding of the service link to third
parties. Use the rented instance first for private integration testing. Do not
open it to public ArtMentor visitors unless AutoDL confirms that the selected
product and account authorization permit that use. AutoDL Elastic Deployment is
the service-oriented product, but it currently requires enterprise verification.

Official references:

- https://www.autodl.com/docs/service_agreement/
- https://www.autodl.com/docs/port/
- https://www.autodl.com/docs/elastic_deploy/
- https://www.autodl.com/docs/price/

## Phase A: first GPU startup and compatibility check

Starting the instance begins hourly billing. In the AutoDL console, start the
instance in normal GPU mode, open its terminal, and run:

```bash
python - <<'PY'
import sys, torch
print("python", sys.version.split()[0])
print("torch", torch.__version__)
print("torch cuda build", torch.version.cuda)
print("gpu available", torch.cuda.is_available())
print("gpu", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none")
PY
```

The rented instance was checked as Python 3.12.3, PyTorch 2.3.0+cu121, CUDA
12.1, with an available RTX 4080 SUPER. This base is sufficient. The installer
does not modify it: it creates a separate Conda environment containing the
frozen Python 3.10 / PyTorch 2.1 / CUDA 12.1 stack used by the existing worker.

## Phase B: copy code and install once

After the cloud-ready files are published to the repository, clone or update
the repository on AutoDL. From the repository root run:

```bash
bash pose_worker/install_autodl.sh
```

The installer creates an isolated Conda environment under
`/root/autodl-tmp/ArtMentorPose`, installs Python 3.10, PyTorch 2.1/CUDA 12.1
and the frozen MMPose line, checks out the MMPose 1.3.2 config commit, downloads
the 52 MiB RTMPose checkpoint, verifies its SHA-256, and prints the installed
versions. This is a one-time operation; the normal container instance retains
its data while powered off.

MMPose 1.3.2 is installed without its obsolete Chumpy metadata dependency.
Chumpy is only relevant to other legacy parametric-body paths and is not
imported by this 2D RTMPose service. The actual 2D inference dependencies are
pinned explicitly in `requirements-cloud.txt`.

## Phase C: create the shared secret

Copy the example file:

```bash
cp pose_worker/.env.example pose_worker/.env
```

Generate one long random token and replace the placeholder in that file:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Keep one private copy. The same value is later entered into Render as
`POSE_WORKER_TOKEN`. Do not commit the `.env` file or paste the token into chat.

## Phase D: start and verify inside AutoDL

Run the service in `tmux` so closing SSH does not terminate it:

```bash
tmux new -s pose-worker
bash pose_worker/start.sh
```

Wait until Uvicorn reports application startup complete. In a second terminal:

```bash
curl http://127.0.0.1:6006/health
```

The required fields are:

```json
{"status":"ok","model_ready":true,"auth_ready":true,"device":"cuda:0"}
```

Use `Ctrl+B`, then `D`, to detach from tmux. Re-enter later with:

```bash
tmux attach -t pose-worker
```

## Phase E: verify one real image

Place one test figure image on the instance, load the private environment, and
run the supplied smoke test against the internal address:

```bash
set -a
source pose_worker/.env
set +a
python -m pose_worker.smoke_test \
  --url http://127.0.0.1:6006 \
  --image /path/to/test-figure.png
```

Success reports `status: ok`, 17 keypoints, and mean confidence. The smoke test
does not save the source image in the worker log.

## Phase F: obtain the AutoDL HTTPS address

In the AutoDL console open **Custom Service**, choose the HTTP mapping for port
6006, and copy the HTTPS base address. Open `<base-address>/health` and confirm
the same readiness fields. The address is not a secret, but the Bearer token is.

For a normal container instance, keep this test restricted to the account
holder as required by AutoDL's custom-service agreement.

## Phase G: connect Render for an authorized deployment

In the existing Render web service, set:

```text
POSE_FEATURE_ENABLED=true
POSE_PROVIDER=worker
POSE_WORKER_URL=<AutoDL HTTPS base address, without /health>
POSE_WORKER_TOKEN=<the same private token>
POSE_WORKER_TIMEOUT_SECONDS=45
```

Redeploy ArtMentor, check `/api/health` for `pose_enabled: true`, and run one
Body structure estimate. Confirm that the returned skeleton has 17 editable
points and that a wrong token produces a controlled unavailable message rather
than leaking server details.

## Shutdown behavior

AutoDL container-instance billing stops when the instance is powered off, and
its stored environment is retained according to the platform's current rules.
When the GPU instance is off, ArtMentor's normal critique still works but body
estimation is unavailable. Powering the instance on does not automatically
guarantee that the tmux process restarts; check `/health` before enabling a test.
