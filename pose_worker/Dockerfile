FROM pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ARTMENTOR_POSE_HOME=/opt/artmentor-pose \
    POSE_CONFIG_PATH=/opt/mmpose/configs/body_2d_keypoint/rtmpose/humanart/rtmpose-m_8xb256-420e_humanart-256x192.py \
    POSE_CHECKPOINT_PATH=/opt/artmentor-pose/models/rtmpose-m_8xb256-420e_humanart-256x192-8430627b_20230611.pth \
    POSE_LOG_PATH=/opt/artmentor-pose/runs/platform-worker.jsonl \
    POSE_DEVICE=auto \
    POSE_REQUIRE_CUDA=true \
    POSE_MAX_IMAGE_MB=10 \
    PORT=6006

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pose_worker/requirements-cloud.txt /app/pose_worker/requirements-cloud.txt
RUN python -m pip install --upgrade pip setuptools==75.8.2 wheel \
    && python -m pip install -r /app/pose_worker/requirements-cloud.txt \
    && python -m pip install mmpose==1.3.2 --no-deps \
    && git clone --filter=blob:none https://github.com/open-mmlab/mmpose.git /opt/mmpose \
    && git -C /opt/mmpose checkout 5408bc76f5b848cf925a0d1857899011d8c5b497

COPY pose_worker /app/pose_worker
RUN python -m pose_worker.download_model --destination "${POSE_CHECKPOINT_PATH}" \
    && mkdir -p /opt/artmentor-pose/runs

EXPOSE 6006
HEALTHCHECK --interval=20s --timeout=5s --start-period=90s --retries=5 \
    CMD python -c "import json,urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:6006/health', timeout=3)); assert data['model_ready']"

CMD ["python", "-m", "uvicorn", "pose_worker.app:app", "--host", "0.0.0.0", "--port", "6006", "--workers", "1"]
