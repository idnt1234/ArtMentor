"""Deterministic checks for conservative, no-reference artwork inspection."""

from app.schemas import Rect
from app.services.pose_client import DemoPoseClient
from app.services.pose_inspect import inspect_skeleton


def skeleton():
    result = DemoPoseClient().estimate(
        b"unused", Rect(x=0.05, y=0.03, width=0.9, height=0.94)
    )
    result.confirmed = True
    return result


def test_broadly_regular_skeleton_is_consistent() -> None:
    result = inspect_skeleton(skeleton(), "semi_realistic")
    assert result.overall_status == "consistent"
    assert result.comparable_keypoint_count == 17
    assert "No large" in result.findings[0].title


def test_extreme_forearm_ratio_is_reported_as_suspicious_evidence() -> None:
    artwork = skeleton()
    wrist = next(point for point in artwork.keypoints if point.name == "left_wrist")
    wrist.x = 0.95
    wrist.y = 0.95
    wrist.source = "user"
    wrist.confidence = 1

    result = inspect_skeleton(artwork, "realistic")
    assert result.overall_status == "suspicious"
    assert any(
        {"left_elbow", "left_wrist"}.issubset(finding.keypoints)
        for finding in result.findings
    )
    assert all(finding.observation for finding in result.findings)


def test_unconfirmed_skeleton_refuses_to_judge() -> None:
    artwork = skeleton()
    artwork.confirmed = False
    result = inspect_skeleton(artwork, "realistic")
    assert result.overall_status == "insufficient"
    assert result.comparable_keypoint_count == 0
    assert "Confirm" in result.findings[0].title
