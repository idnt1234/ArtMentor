#!/usr/bin/env bash
set -euo pipefail

worker_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
runtime_home="${ARTMENTOR_POSE_HOME:-/root/autodl-tmp/ArtMentorPose}"
venv_dir="${POSE_VENV_DIR:-${runtime_home}/envs/rtmpose-py310}"
mmpose_dir="${POSE_MMPPOSE_DIR:-${runtime_home}/src/mmpose}"
checkpoint="${runtime_home}/models/rtmpose-m_8xb256-420e_humanart-256x192-8430627b_20230611.pth"
python_bin="${PYTHON_BIN:-python}"

"${python_bin}" - <<'PY'
import torch

if not torch.cuda.is_available():
    raise SystemExit("The AutoDL base environment cannot access a CUDA GPU.")
print(
    "AutoDL GPU verified:",
    torch.cuda.get_device_name(0),
    "base torch",
    torch.__version__,
    "CUDA build",
    torch.version.cuda,
)
PY

mkdir -p "${runtime_home}/envs" "${runtime_home}/src" "${runtime_home}/models" "${runtime_home}/runs"
if [[ ! -x "${venv_dir}/bin/python" ]]; then
    if ! command -v conda >/dev/null 2>&1; then
        echo "Conda is required to create the isolated Python 3.10 environment." >&2
        exit 2
    fi
    conda create --prefix "${venv_dir}" python=3.10 -y
fi

"${venv_dir}/bin/python" -m pip install --upgrade pip setuptools==75.8.2 wheel
"${venv_dir}/bin/python" -m pip install \
    torch==2.1.0 torchvision==0.16.0 \
    --index-url https://download.pytorch.org/whl/cu121
"${venv_dir}/bin/python" -m pip install -r "${worker_root}/requirements-cloud.txt"
"${venv_dir}/bin/python" -m pip install mmpose==1.3.2 --no-deps

if [[ ! -d "${mmpose_dir}/.git" ]]; then
    git clone --filter=blob:none https://github.com/open-mmlab/mmpose.git "${mmpose_dir}"
fi
git -C "${mmpose_dir}" fetch --depth 1 origin 5408bc76f5b848cf925a0d1857899011d8c5b497
git -C "${mmpose_dir}" checkout 5408bc76f5b848cf925a0d1857899011d8c5b497

PYTHONPATH="${worker_root}/.." "${venv_dir}/bin/python" -m pose_worker.download_model \
    --destination "${checkpoint}"

"${venv_dir}/bin/python" - <<'PY'
import mmcv
import mmengine
import mmdet
import mmpose
import numpy
import torch

print("Cloud environment ready:")
print(" torch", torch.__version__, "cuda", torch.version.cuda)
print(" gpu", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none")
print(" numpy", numpy.__version__)
print(" mmcv", mmcv.__version__)
print(" mmengine", mmengine.__version__)
print(" mmdet", mmdet.__version__)
print(" mmpose", mmpose.__version__)
if not torch.cuda.is_available():
    raise SystemExit("The isolated RTMPose environment cannot access the GPU.")
PY

echo "Installation complete. Copy pose_worker/.env.example to pose_worker/.env, add a private token, then run pose_worker/start.sh."
