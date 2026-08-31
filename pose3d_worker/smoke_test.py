"""Small authenticated HTTP smoke test; run after the GPU worker reports healthy."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--skeleton", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("pose3d-smoke-result.json"))
    args = parser.parse_args()
    payload = {
        "image_base64": base64.b64encode(args.image.read_bytes()).decode("ascii"),
        "skeleton": json.loads(args.skeleton.read_text(encoding="utf-8")),
    }
    response = httpx.post(
        args.url.rstrip("/") + "/reconstruct",
        json=payload,
        headers={"Authorization": f"Bearer {args.token}"},
        timeout=240,
    )
    response.raise_for_status()
    args.output.write_text(json.dumps(response.json(), indent=2), encoding="utf-8")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
