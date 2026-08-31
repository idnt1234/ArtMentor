"""Run the production runtime against one frozen Stage 2 evidence record."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import cv2

try:
    from .inference import COCO17, Pose3DRuntime
except ImportError:
    from inference import COCO17, Pose3DRuntime


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    image_path = Path(evidence["source_image"])
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f"Image not found: {image_path}")
    height, width = image.shape[:2]
    x1, y1, x2, y2 = evidence["bbox_xyxy"]
    source_points = {point["name"]: point for point in evidence["keypoints"]["items"]}
    skeleton = {
        "bbox": {
            "x": x1 / width,
            "y": y1 / height,
            "width": (x2 - x1) / width,
            "height": (y2 - y1) / height,
        },
        "keypoints": [
            {
                "name": name,
                "x": source_points[name]["x"] / width,
                "y": source_points[name]["y"] / height,
                "confidence": 1,
                "source": "user",
                "visibility": (
                    "visible"
                    if source_points[name]["visibility"] == "visible"
                    else "hidden"
                ),
            }
            for name in COCO17
        ],
        "confirmed": True,
        "warnings": [],
        "model": "frozen-stage1-evidence",
    }
    runtime = Pose3DRuntime()
    runtime.load()
    result = runtime.reconstruct(image_path.read_bytes(), skeleton)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, encoded in result.pop("views").items():
        filename = name.removesuffix("_base64") + ".png"
        (args.output / filename).write_bytes(base64.b64decode(encoded))
    (args.output / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
