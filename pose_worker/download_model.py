"""Download the frozen RTMPose checkpoint and verify it before use."""

from __future__ import annotations

import argparse
import hashlib
import os
import urllib.request
from pathlib import Path

try:
    from .inference import CHECKPOINT_NAME, CHECKPOINT_SHA256
except ImportError:
    from inference import CHECKPOINT_NAME, CHECKPOINT_SHA256

DEFAULT_URL = (
    "https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/"
    + CHECKPOINT_NAME
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(destination: Path, url: str = DEFAULT_URL) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and sha256(destination) == CHECKPOINT_SHA256:
        print(f"RTMPose checkpoint already verified: {destination}")
        return destination

    partial = destination.with_suffix(destination.suffix + ".part")
    if partial.exists():
        partial.unlink()
    print(f"Downloading RTMPose checkpoint to {destination}")
    try:
        urllib.request.urlretrieve(url, partial)
        actual = sha256(partial)
        if actual != CHECKPOINT_SHA256:
            raise RuntimeError(
                f"Checkpoint checksum mismatch: expected {CHECKPOINT_SHA256}, "
                f"received {actual}."
            )
        os.replace(partial, destination)
    finally:
        if partial.exists():
            partial.unlink()
    print("RTMPose checkpoint checksum verified.")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args()
    download(args.destination, args.url)


if __name__ == "__main__":
    main()
