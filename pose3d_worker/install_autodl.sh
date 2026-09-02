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
SOURCE_MARKER="$SAM_REPO/.artmentor-source-commit"
if [[ -f "$SOURCE_MARKER" ]] && [[ "$(cat "$SOURCE_MARKER")" == "$SAM_COMMIT" ]]; then
  echo "SAM 3D Body source is already pinned at $SAM_COMMIT."
elif [[ -d "$SAM_REPO/.git" ]]; then
  git -C "$SAM_REPO" fetch --depth 1 origin "$SAM_COMMIT"
  git -C "$SAM_REPO" checkout --detach FETCH_HEAD
  printf '%s\n' "$SAM_COMMIT" > "$SOURCE_MARKER"
else
  # AutoDL's route to GitHub occasionally drops git's HTTP stream. The
  # immutable codeload archive is the same source and is much more reliable.
  SOURCE_ARCHIVE="$POSE_HOME/src/sam-3d-body-$SAM_COMMIT.tar.gz"
  if [[ -e "$SAM_REPO" ]]; then
    mv "$SAM_REPO" "$SAM_REPO.incomplete.$(date +%s)"
  fi
  curl --fail --location --retry 5 --retry-delay 3 \
    "https://codeload.github.com/facebookresearch/sam-3d-body/tar.gz/$SAM_COMMIT" \
    --output "$SOURCE_ARCHIVE"
  mkdir -p "$SAM_REPO"
  tar -xzf "$SOURCE_ARCHIVE" --strip-components=1 -C "$SAM_REPO"
  rm -f "$SOURCE_ARCHIVE"
  printf '%s\n' "$SAM_COMMIT" > "$SOURCE_MARKER"
fi

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
if "$PYTHON" -c 'import detectron2' >/dev/null 2>&1; then
  echo "Detectron2 is already installed; skipping the GitHub rebuild."
else
  "$PYTHON" -m pip install \
    'git+https://github.com/facebookresearch/detectron2.git@a1ce2f9' \
    --no-build-isolation --no-deps
fi
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
