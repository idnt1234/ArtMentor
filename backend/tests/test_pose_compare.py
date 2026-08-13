"""Deterministic checks for the reference-skeleton geometry engine."""

from app.schemas import Rect
from app.services.pose_client import DemoPoseClient
from app.services.pose_compare import compare_skeletons


def skeleton():
    result = DemoPoseClient().estimate(b"unused", Rect(x=0.05, y=0.03, width=0.9, height=0.94))
    result.confirmed = True
    return result


def test_matching_confirmed_skeletons_are_consistent() -> None:
    result = compare_skeletons(skeleton(), skeleton(), "realistic")
    assert result.overall_status == "consistent"
    assert result.comparable_keypoint_count == 17
    assert result.findings[0].status == "consistent"


def test_moved_wrist_produces_numeric_reference_evidence() -> None:
    artwork = skeleton()
    reference = skeleton()
    wrist = next(point for point in artwork.keypoints if point.name == "left_wrist")
    wrist.x = 0.52
    wrist.y = 0.72
    wrist.source = "user"
    wrist.confidence = 1

    result = compare_skeletons(artwork, reference, "realistic")
    assert result.overall_status == "suspicious"
    assert any("left_wrist" in finding.keypoints for finding in result.findings)
    assert all(finding.difference for finding in result.findings)


def test_unconfirmed_skeletons_refuse_to_judge() -> None:
    artwork = skeleton()
    artwork.confirmed = False
    result = compare_skeletons(artwork, skeleton(), "realistic")
    assert result.overall_status == "insufficient"
    assert "Confirm" in result.findings[0].title
