# ArtMentor Pose Worker

This service keeps RTMPose-M/Human-Art loaded on one GPU. The main ArtMentor
web process sends an image plus a user-selected person box and receives an
editable, image-normalized COCO-17 skeleton. Raw images stay in memory; the
worker log records only a SHA-256 hash and inference metadata.

## Security and API contract

- `GET /health` is public and reports model/auth readiness without exposing a
  secret.
- `POST /estimate` requires `Authorization: Bearer <token>` unless the
  loopback-only Windows script explicitly enables unauthenticated local mode.
- The default image limit is 10 MiB.
- One Uvicorn worker process must be used. GPU inference is serialized inside
  that process.

The production web server uses the same value in `POSE_WORKER_TOKEN` that the
GPU process receives as `POSE_WORKER_API_TOKEN`. Never put either value in the
frontend, source code, screenshots, or chat messages.

## Existing Windows workstation

The existing environment remains supported:

```powershell
.\pose_worker\start.ps1
```

It binds to `127.0.0.1:8011`, requires CUDA, and explicitly permits
unauthenticated requests only because it is loopback-only.

## AutoDL installation

AutoDL cannot import an external custom Docker image into a normal container
instance. The installer creates an isolated Python 3.10 / PyTorch 2.1 / CUDA
12.1 environment without changing the instance's base Python/PyTorch. Run:

```bash
bash pose_worker/install_autodl.sh
cp pose_worker/.env.example pose_worker/.env
```

Replace the token placeholder in `pose_worker/.env`, then start the worker:

```bash
bash pose_worker/start.sh
```

It listens on `0.0.0.0:6006`, the standard AutoDL custom-service port. Full
operator instructions are in `docs/AUTODL_POSE_WORKER.md`.

## Portable Docker build

The Dockerfile is retained for GPU providers that accept external images:

```bash
docker build -f pose_worker/Dockerfile -t artmentor-pose-worker .
docker run --rm --gpus all -p 6006:6006 \
  -e POSE_WORKER_API_TOKEN='<private token>' \
  artmentor-pose-worker
```

The image freezes the same model family and dependency line used by the local
research worker. The checkpoint is downloaded from OpenMMLab during the build
and accepted only when its SHA-256 matches the frozen value.
