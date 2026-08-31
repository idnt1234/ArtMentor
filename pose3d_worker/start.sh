#!/usr/bin/env bash
set -euo pipefail

WORKER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$WORKER_ROOT"

: "${POSE3D_WORKER_API_TOKEN:?Set POSE3D_WORKER_API_TOKEN before starting the worker}"
export ARTMENTOR_POSE3D_HOME="${ARTMENTOR_POSE3D_HOME:-$HOME/ArtMentorPose}"
export SAM3D_REPO="${SAM3D_REPO:-$ARTMENTOR_POSE3D_HOME/src/sam-3d-body}"
export SAM3D_CHECKPOINT_DIR="${SAM3D_CHECKPOINT_DIR:-$ARTMENTOR_POSE3D_HOME/models/sam-3d-body-vith}"

exec python -m uvicorn pose3d_worker.app:app --host 0.0.0.0 --port "${POSE3D_PORT:-6008}" --workers 1
