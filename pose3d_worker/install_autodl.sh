#!/usr/bin/env bash
set -euo pipefail

# Installs the isolated Python 3.11 runtime. It deliberately does not start a
# public service and never writes a Hugging Face token to the repository.
ARTMENTOR_REPO="${ARTMENTOR_REPO:-$PWD}"
POSE_HOME="${ARTMENTOR_POSE3D_HOME:-$HOME/ArtMentorPose}"
SAM_REPO="$POSE_HOME/src/sam-3d-body"
CHECKPOINT_DIR="$POSE_HOME/models/sam-3d-body-vith"
ENV_NAME="${POSE3D_CONDA_ENV:-sam3d-body}"
SAM_COMMIT="b5c765a0d89d789985e186d396315e7590887b94"

if ! command -v conda >/dev/null 2>&1; then
  echo "conda is required (AutoDL images normally include it)." >&2
  exit 1
fi

mkdir -p "$POSE_HOME/src" "$POSE_HOME/models" "$POSE_HOME/runs"
if [[ ! -d "$SAM_REPO/.git" ]]; then
  git clone https://github.com/facebookresearch/sam-3d-body.git "$SAM_REPO"
fi
git -C "$SAM_REPO" fetch --all --tags
git -C "$SAM_REPO" checkout --detach "$SAM_COMMIT"

if ! conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  conda create -n "$ENV_NAME" python=3.11 -y
fi

PYTHON="$(conda run -n "$ENV_NAME" which python)"
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cu126
"$PYTHON" -m pip install \
  pytorch-lightning pyrender opencv-python-headless yacs scikit-image einops timm \
  dill pandas rich hydra-core hydra-submitit-launcher hydra-colorlog pyrootutils \
  webdataset chump networkx==3.2.1 roma joblib seaborn wandb appdirs ffmpeg \
  cython jsonlines xtcocotools loguru optree fvcore pycocotools tensorboard \
  huggingface_hub
"$PYTHON" -m pip install \
  'git+https://github.com/facebookresearch/detectron2.git@a1ce2f9' \
  --no-build-isolation --no-deps
"$PYTHON" -m pip install -r "$ARTMENTOR_REPO/pose3d_worker/requirements-service.txt"

if [[ ! -f "$CHECKPOINT_DIR/model.ckpt" || ! -f "$CHECKPOINT_DIR/assets/mhr_model.pt" ]]; then
  cat >&2 <<EOF

Runtime installed, but the gated model is not present at:
  $CHECKPOINT_DIR

After your Hugging Face account has accepted the SAM license and received access,
download it without committing a token:
  conda run -n $ENV_NAME hf auth login
  conda run -n $ENV_NAME hf download facebook/sam-3d-body-vith --local-dir "$CHECKPOINT_DIR"

Then rerun this installer; it will verify the runtime path without redownloading packages.
EOF
  exit 2
fi

echo "SAM 3D Body environment is ready."
echo "Start it with: conda run -n $ENV_NAME bash $ARTMENTOR_REPO/pose3d_worker/start.sh"
