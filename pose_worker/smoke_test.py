"""Send one real image through a running pose worker."""

from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Worker base URL")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--token", default=os.environ.get("POSE_WORKER_API_TOKEN"))
    args = parser.parse_args()
    if not args.token:
        raise SystemExit("POSE_WORKER_API_TOKEN or --token is required.")
    if not args.image.is_file():
        raise SystemExit(f"Image not found: {args.image}")

    payload = json.dumps(
        {
            "image_base64": base64.b64encode(args.image.read_bytes()).decode("ascii"),
            "bbox": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        args.url.rstrip("/") + "/estimate",
        data=payload,
        headers={
            "Authorization": f"Bearer {args.token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Worker returned HTTP {exc.code}: {detail}") from exc
    keypoints = result.get("keypoints", [])
    if len(keypoints) != 17:
        raise SystemExit(f"Expected 17 keypoints, received {len(keypoints)}.")
    mean_confidence = sum(float(point["confidence"]) for point in keypoints) / 17
    print(
        json.dumps(
            {
                "status": "ok",
                "model": result.get("model"),
                "keypoints": len(keypoints),
                "mean_confidence": round(mean_confidence, 6),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
