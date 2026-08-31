"""Persistent SAM 3D Body runtime and evidence-oriented PNG rendering."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np


COCO17 = (
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
)
COCO_TO_MHR70 = np.asarray(
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 62, 41, 9, 10, 11, 12, 13, 14],
    dtype=np.int64,
)
COCO17_EDGES = (
    ("nose", "left_eye"), ("nose", "right_eye"),
    ("left_eye", "left_ear"), ("right_eye", "right_ear"),
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"), ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"), ("right_knee", "right_ankle"),
)
CHECKPOINT_SHA256 = "3b1cb897f4bbd977bf81cbb0b30780a9582681ac642ee112865790ceb4d66056"
MHR_SHA256 = "352e271a6c42729c68554ceaea0c955e866970160c31e35506d782dc0f7377bc"
SAM3D_COMMIT = "b5c765a0d89d789985e186d396315e7590887b94"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _png_base64(image: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".png", image, [cv2.IMWRITE_PNG_COMPRESSION, 5])
    if not ok:
        raise RuntimeError("Could not encode a 3D evidence view.")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def _point_color(name: str) -> tuple[int, int, int]:
    if name.startswith("left"):
        return (50, 115, 225)
    if name.startswith("right"):
        return (225, 105, 55)
    return (65, 180, 85)


def _render_mesh_view(
    vertices: np.ndarray,
    faces: np.ndarray,
    keypoints: np.ndarray,
    horizontal_axis: int,
    vertical_axis: int,
    depth_axis: int,
    title: str,
) -> np.ndarray:
    canvas = np.full((900, 900, 3), 248, dtype=np.uint8)
    projected = np.asarray(vertices[:, [horizontal_axis, vertical_axis]], np.float32)
    minimum, maximum = projected.min(axis=0), projected.max(axis=0)
    extent = np.maximum(maximum - minimum, 1e-6)
    scale = 720.0 / float(max(extent))
    center = (minimum + maximum) * 0.5
    screen = (projected - center) * scale + np.array([450.0, 470.0], np.float32)

    triangles = np.asarray(faces, np.int32)
    tri_vertices = vertices[triangles]
    normals = np.cross(
        tri_vertices[:, 1] - tri_vertices[:, 0],
        tri_vertices[:, 2] - tri_vertices[:, 0],
    )
    normal_length = np.maximum(np.linalg.norm(normals, axis=1), 1e-8)
    lighting = 0.38 + 0.62 * np.abs(normals[:, depth_axis]) / normal_length
    face_depth = tri_vertices[:, :, depth_axis].mean(axis=1)
    for face_index in np.argsort(-face_depth):
        polygon = np.rint(screen[triangles[face_index]]).astype(np.int32)
        shade = int(np.clip(205.0 * lighting[face_index], 70.0, 220.0))
        cv2.fillConvexPoly(
            canvas,
            polygon,
            (shade, int(shade * 0.93), int(shade * 0.82)),
            lineType=cv2.LINE_AA,
        )

    joint_screen = (
        np.asarray(keypoints[:, [horizontal_axis, vertical_axis]], np.float32) - center
    ) * scale + np.array([450.0, 470.0], np.float32)
    index_by_name = {name: index for index, name in enumerate(COCO17)}
    for first, second in COCO17_EDGES:
        p1 = tuple(np.rint(joint_screen[index_by_name[first]]).astype(int))
        p2 = tuple(np.rint(joint_screen[index_by_name[second]]).astype(int))
        cv2.line(canvas, p1, p2, (35, 35, 35), 3, cv2.LINE_AA)
    for index, name in enumerate(COCO17):
        point = tuple(np.rint(joint_screen[index]).astype(int))
        cv2.circle(canvas, point, 6, _point_color(name), -1, cv2.LINE_AA)
    cv2.putText(canvas, title, (28, 45), cv2.FONT_HERSHEY_SIMPLEX, .9, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(
        canvas,
        "single-image hypothesis - not 3D ground truth",
        (28, 875),
        cv2.FONT_HERSHEY_SIMPLEX,
        .65,
        (55, 55, 55),
        1,
        cv2.LINE_AA,
    )
    return canvas


def _render_overlay(
    image: np.ndarray,
    bbox_xyxy: np.ndarray,
    reviewed_xy: np.ndarray,
    predicted_xy: np.ndarray,
    reviewed: np.ndarray,
) -> np.ndarray:
    canvas = image.copy()
    bbox = np.rint(bbox_xyxy).astype(int)
    cv2.rectangle(canvas, tuple(bbox[:2]), tuple(bbox[2:]), (0, 190, 255), 2)
    for index, name in enumerate(COCO17):
        if not reviewed[index]:
            continue
        truth = tuple(np.rint(reviewed_xy[index]).astype(int))
        prediction = tuple(np.rint(predicted_xy[index]).astype(int))
        cv2.line(canvas, truth, prediction, (255, 150, 0), 1, cv2.LINE_AA)
        cv2.circle(canvas, truth, 5, _point_color(name), -1, cv2.LINE_AA)
        cv2.circle(canvas, prediction, 5, (255, 0, 255), 2, cv2.LINE_AA)
    cv2.rectangle(canvas, (14, 14), (430, 77), (248, 248, 248), -1)
    cv2.putText(canvas, "filled = confirmed 2D / ring = 3D projection", (25, 42), cv2.FONT_HERSHEY_SIMPLEX, .56, (30, 30, 30), 1, cv2.LINE_AA)
    cv2.putText(canvas, "line length measures 2D agreement only", (25, 65), cv2.FONT_HERSHEY_SIMPLEX, .52, (65, 65, 65), 1, cv2.LINE_AA)
    return canvas


class Pose3DRuntime:
    """Load the gated model once and serialize all GPU work."""

    def __init__(self) -> None:
        default_home = Path(__file__).resolve().parents[1]
        self.home = Path(os.environ.get("ARTMENTOR_POSE3D_HOME", default_home))
        self.repo = Path(
            os.environ.get("SAM3D_REPO", self.home / "src" / "sam-3d-body")
        )
        self.checkpoint_dir = Path(
            os.environ.get(
                "SAM3D_CHECKPOINT_DIR", self.home / "models" / "sam-3d-body-vith"
            )
        )
        self.log_path = Path(
            os.environ.get(
                "POSE3D_LOG_PATH", self.home / "runs" / "pose3d-worker.jsonl"
            )
        )
        self.estimator: Any = None
        self.prepare_batch: Any = None
        self.recursive_to: Any = None
        self.torch: Any = None
        self.device = "uninitialized"
        self._lock = threading.Lock()
        self._log_lock = threading.Lock()

    def load(self) -> None:
        checkpoint = self.checkpoint_dir / "model.ckpt"
        mhr = self.checkpoint_dir / "assets" / "mhr_model.pt"
        config = self.checkpoint_dir / "model_config.yaml"
        for path in (checkpoint, mhr, config):
            if not path.is_file():
                raise FileNotFoundError(f"Required SAM 3D Body file is missing: {path}")
        if os.environ.get("POSE3D_SKIP_CHECKSUM", "").lower() not in {"1", "true", "yes"}:
            if _file_sha256(checkpoint) != CHECKPOINT_SHA256:
                raise RuntimeError("SAM 3D Body checkpoint checksum mismatch.")
            if _file_sha256(mhr) != MHR_SHA256:
                raise RuntimeError("MHR model checksum mismatch.")

        os.environ["MOMENTUM_ENABLED"] = "0"
        if str(self.repo) not in sys.path:
            sys.path.insert(0, str(self.repo))
        import torch
        from sam_3d_body import SAM3DBodyEstimator, load_sam_3d_body
        from sam_3d_body.data.utils.prepare_batch import prepare_batch
        from sam_3d_body.utils import recursive_to

        if not torch.cuda.is_available():
            raise RuntimeError("SAM 3D Body preview requires a CUDA GPU.")
        self.device = "cuda:0"
        model, model_cfg = load_sam_3d_body(
            str(checkpoint), device=torch.device(self.device), mhr_path=str(mhr)
        )
        self.estimator = SAM3DBodyEstimator(
            sam_3d_body_model=model,
            model_cfg=model_cfg,
            human_detector=None,
            human_segmentor=None,
            fov_estimator=None,
        )
        self.prepare_batch = prepare_batch
        self.recursive_to = recursive_to
        self.torch = torch

    def reconstruct(self, image_bytes: bytes, skeleton: dict[str, Any]) -> dict[str, Any]:
        if self.estimator is None or self.torch is None:
            raise RuntimeError("SAM 3D Body is not loaded.")
        encoded = np.frombuffer(image_bytes, np.uint8)
        image_bgr = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image_bgr is None:
            raise ValueError("OpenCV could not decode the image.")
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        height, width = image_bgr.shape[:2]
        box = skeleton["bbox"]
        bbox = np.asarray(
            [[
                box["x"] * width,
                box["y"] * height,
                (box["x"] + box["width"]) * width,
                (box["y"] + box["height"]) * height,
            ]],
            np.float32,
        )
        points_by_name = {point["name"]: point for point in skeleton["keypoints"]}
        target_xy = np.asarray(
            [[points_by_name[name]["x"] * width, points_by_name[name]["y"] * height] for name in COCO17],
            np.float32,
        )
        reviewed = np.asarray(
            [points_by_name[name]["visibility"] not in {"hidden", "unknown"} for name in COCO17],
            bool,
        )

        started = time.perf_counter()
        with self._lock, self.torch.no_grad():
            batch = self.prepare_batch(
                image_rgb, self.estimator.transform, bbox, None, None
            )
            batch = self.recursive_to(batch, self.device)
            self.estimator.model._initialize_batch(batch)
            pose_output = self.estimator.model.run_inference(
                image_rgb,
                batch,
                inference_type="body",
                transform_hand=self.estimator.transform_hand,
                thresh_wrist_angle=self.estimator.thresh_wrist_angle,
            )
            baseline_2d = (
                pose_output["mhr"]["pred_keypoints_2d"][0, COCO_TO_MHR70]
                .detach().float().cpu().numpy()
            )
            target_tensor = self.torch.as_tensor(
                target_xy, dtype=batch["img"].dtype, device=batch["img"].device
            ).unsqueeze(0)
            crop_xy = self.estimator.model._full_to_crop(batch, target_tensor)[0]
            within_crop = self.torch.all(
                (crop_xy >= -0.5) & (crop_xy <= 0.5), dim=1
            ).cpu().numpy()
            baseline_errors = np.linalg.norm(baseline_2d - target_xy, axis=1)
            eligible = reviewed & within_crop & np.isfinite(baseline_errors)
            selected = np.asarray(
                [index for index in np.argsort(-baseline_errors, kind="stable") if eligible[index]][:2],
                np.int64,
            )
            if selected.size:
                selected_tensor = self.torch.as_tensor(
                    selected, dtype=self.torch.long, device=batch["img"].device
                )
                prompt_xy = self.torch.clamp(crop_xy[selected_tensor] + 0.5, 0.0, 1.0)
                prompt_labels = self.torch.as_tensor(
                    COCO_TO_MHR70[selected],
                    dtype=prompt_xy.dtype,
                    device=prompt_xy.device,
                ).unsqueeze(1)
                keypoint_prompt = self.torch.cat(
                    [prompt_xy, prompt_labels], dim=1
                ).unsqueeze(0)
                pose_output, _ = self.estimator.model.run_keypoint_prompt(
                    batch, pose_output, keypoint_prompt
                )
            out = self.recursive_to(
                self.recursive_to(pose_output["mhr"], "cpu"), "numpy"
            )
            if self.device.startswith("cuda"):
                self.torch.cuda.synchronize()
        elapsed = time.perf_counter() - started

        predicted_2d = np.asarray(out["pred_keypoints_2d"][0])[COCO_TO_MHR70]
        predicted_3d = np.asarray(out["pred_keypoints_3d"][0])[COCO_TO_MHR70]
        vertices = np.asarray(out["pred_vertices"][0], np.float32)
        faces = np.asarray(self.estimator.faces, np.int32)
        diagonal = float(np.linalg.norm(bbox[0, 2:4] - bbox[0, :2]))
        distances = np.linalg.norm(predicted_2d - target_xy, axis=1)
        mean_error = float(distances[reviewed].mean()) if reviewed.any() else None

        result = {
            "model": "facebook/sam-3d-body-vith",
            "metrics": {
                "bbox_diagonal_px": round(diagonal, 4),
                "reviewed_keypoint_count": int(reviewed.sum()),
                "mean_projection_error_px": round(mean_error, 4) if mean_error is not None else None,
                "mean_projection_error_normalized": round(mean_error / diagonal, 8) if mean_error is not None else None,
            },
            "prompted_joints": [COCO17[index] for index in selected],
            "inference_seconds": round(elapsed, 6),
            "limitations": [
                "This is one depth hypothesis inferred from a single image, not measured 3D ground truth.",
                "A low 2D projection error only shows image-plane agreement; hidden depth can still be wrong.",
                "Clothing, occlusion, stylization and unusual camera perspective can change the recovered surface.",
                "No anatomy diagnosis or correctness verdict is generated from this preview.",
            ],
            "views": {
                "overlay_base64": _png_base64(_render_overlay(image_bgr, bbox[0], target_xy, predicted_2d, reviewed)),
                "camera_base64": _png_base64(_render_mesh_view(vertices, faces, predicted_3d, 0, 1, 2, "SAM 3D Body - camera view")),
                "side_base64": _png_base64(_render_mesh_view(vertices, faces, predicted_3d, 2, 1, 0, "SAM 3D Body - side hypothesis")),
                "top_base64": _png_base64(_render_mesh_view(vertices, faces, predicted_3d, 0, 2, 1, "SAM 3D Body - top hypothesis")),
            },
        }
        self._append_record(
            {
                "schema_version": "artmentor.pose3d-worker.v1",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
                "image_width": width,
                "image_height": height,
                "bbox_xyxy": bbox[0].tolist(),
                "model": result["model"],
                "sam3d_commit": SAM3D_COMMIT,
                "device": self.device,
                "inference_seconds": result["inference_seconds"],
                "reviewed_keypoint_count": result["metrics"]["reviewed_keypoint_count"],
                "mean_projection_error_normalized": result["metrics"]["mean_projection_error_normalized"],
                "prompted_joints": result["prompted_joints"],
            }
        )
        return result

    def _append_record(self, record: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_lock, self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
