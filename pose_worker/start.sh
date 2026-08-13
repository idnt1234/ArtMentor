#!/usr/bin/env bash
set -euo pipefail

worker_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${worker_root}/.." && pwd)"
if [[ -f "${worker_root}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "${worker_root}/.env"
    set +a
fi

runtime_home="${ARTMENTOR_POSE_HOME:-/root/autodl-tmp/ArtMentorPose}"
venv_dir="${POSE_VENV_DIR:-${runtime_home}/envs/rtmpose-py310}"
export ARTMENTOR_POSE_HOME="${runtime_home}"
export POSE_CONFIG_PATH="${POSE_CONFIG_PATH:-${runtime_home}/src/mmpose/configs/body_2d_keypoint/rtmpose/humanart/rtmpose-m_8xb256-420e_humanart-256x192.py}"
export POSE_CHECKPOINT_PATH="${POSE_CHECKPOINT_PATH:-${runtime_home}/models/rtmpose-m_8xb256-420e_humanart-256x192-8430627b_20230611.pth}"
export POSE_LOG_PATH="${POSE_LOG_PATH:-${runtime_home}/runs/platform-worker.jsonl}"
export POSE_DEVICE="${POSE_DEVICE:-auto}"
export POSE_REQUIRE_CUDA="${POSE_REQUIRE_CUDA:-true}"
export POSE_MAX_IMAGE_MB="${POSE_MAX_IMAGE_MB:-10}"

if [[ -z "${POSE_WORKER_API_TOKEN:-}" ]]; then
    echo "POSE_WORKER_API_TOKEN is required for a network-accessible worker." >&2
    exit 2
fi
if [[ ! -x "${venv_dir}/bin/python" ]]; then
    echo "Pose virtual environment is missing. Run pose_worker/install_autodl.sh first." >&2
    exit 2
fi

cd "${repo_root}"
exec "${venv_dir}/bin/python" -m uvicorn pose_worker.app:app \
    --host 0.0.0.0 \
    --port "${PORT:-6006}" \
    --workers 1 \
    --proxy-headers \
    --forwarded-allow-ips="*"
