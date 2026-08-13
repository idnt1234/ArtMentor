"""Conservative 2D geometry checks between two user-confirmed COCO-17 skeletons."""

from __future__ import annotations

import math

from ..schemas import (
    PoseComparisonResult,
    PoseFinding,
    PoseKeypoint,
    PoseSkeleton,
    PoseStyleMode,
)

SEGMENTS = {
    "left upper arm": ("left_shoulder", "left_elbow"),
    "left forearm": ("left_elbow", "left_wrist"),
    "right upper arm": ("right_shoulder", "right_elbow"),
    "right forearm": ("right_elbow", "right_wrist"),
    "left thigh": ("left_hip", "left_knee"),
    "left lower leg": ("left_knee", "left_ankle"),
    "right thigh": ("right_hip", "right_knee"),
    "right lower leg": ("right_knee", "right_ankle"),
}
JOINTS = {
    "left elbow": ("left_shoulder", "left_elbow", "left_wrist"),
    "right elbow": ("right_shoulder", "right_elbow", "right_wrist"),
    "left knee": ("left_hip", "left_knee", "left_ankle"),
    "right knee": ("right_hip", "right_knee", "right_ankle"),
}
STYLE_SCALE: dict[PoseStyleMode, float] = {
    "realistic": 1.0,
    "semi_realistic": 1.15,
    "stylized": 1.45,
    "intentional_distortion": 1.9,
}


def _points(skeleton: PoseSkeleton) -> dict[str, PoseKeypoint]:
    return {point.name: point for point in skeleton.keypoints}


def _usable(point: PoseKeypoint) -> bool:
    return point.visibility != "hidden" and (
        point.source == "user" or point.confidence >= 0.3
    )


def _distance(a: PoseKeypoint, b: PoseKeypoint) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _angle(a: PoseKeypoint, b: PoseKeypoint, c: PoseKeypoint) -> float:
    first = (a.x - b.x, a.y - b.y)
    second = (c.x - b.x, c.y - b.y)
    denom = math.hypot(*first) * math.hypot(*second)
    if denom < 1e-9:
        return 0.0
    cosine = max(-1.0, min(1.0, (first[0] * second[0] + first[1] * second[1]) / denom))
    return math.degrees(math.acos(cosine))


def _confidence(*points: PoseKeypoint) -> float:
    scores = [1.0 if item.source == "user" else item.confidence for item in points]
    return round(min(scores), 3)


def compare_skeletons(
    artwork: PoseSkeleton,
    reference: PoseSkeleton,
    style_mode: PoseStyleMode,
) -> PoseComparisonResult:
    """Compare pose geometry only after both skeletons have been confirmed."""
    assumptions = [
        "The artwork and reference depict the intended same pose and person.",
        "This is a 2D keypoint comparison; foreshortening and depth are not reconstructed.",
        f"Tolerance uses the {style_mode.replace('_', ' ')} profile.",
    ]
    if not artwork.confirmed or not reference.confirmed:
        return PoseComparisonResult(
            overall_status="insufficient",
            assumptions=assumptions,
            findings=[
                PoseFinding(
                    status="insufficient",
                    category="evidence",
                    title="Confirm both skeletons first",
                    observation="At least one skeleton is still unconfirmed.",
                    reference="Both skeletons confirmed by the user",
                    difference="Comparison not run",
                    confidence=1,
                    suggestion="Drag uncertain joints into place, mark hidden points, then confirm both sides.",
                )
            ],
            comparable_keypoint_count=0,
            tolerance_mode=style_mode,
        )

    art = _points(artwork)
    ref = _points(reference)
    comparable = [
        name for name in art if _usable(art[name]) and _usable(ref[name])
    ]
    if len(comparable) < 10:
        return PoseComparisonResult(
            overall_status="insufficient",
            assumptions=assumptions,
            findings=[
                PoseFinding(
                    status="insufficient",
                    category="evidence",
                    title="Too few reliable joints",
                    observation=f"Only {len(comparable)} of 17 points can be compared.",
                    reference="At least 10 visible or user-corrected points",
                    difference=f"{10 - len(comparable)} points missing",
                    keypoints=comparable,
                    confidence=0.95,
                    suggestion="Correct low-confidence points or mark the genuinely hidden joints before retrying.",
                )
            ],
            comparable_keypoint_count=len(comparable),
            tolerance_mode=style_mode,
        )

    scale = STYLE_SCALE[style_mode]
    findings: list[PoseFinding] = []

    # Compare corresponding limb proportions after normalizing by shoulder-to-hip torso length.
    def torso(points: dict[str, PoseKeypoint]) -> float:
        shoulder_x = (points["left_shoulder"].x + points["right_shoulder"].x) / 2
        shoulder_y = (points["left_shoulder"].y + points["right_shoulder"].y) / 2
        hip_x = (points["left_hip"].x + points["right_hip"].x) / 2
        hip_y = (points["left_hip"].y + points["right_hip"].y) / 2
        return max(math.hypot(shoulder_x - hip_x, shoulder_y - hip_y), 1e-6)

    art_torso, ref_torso = torso(art), torso(ref)
    for label, (start, end) in SEGMENTS.items():
        required = (art[start], art[end], ref[start], ref[end])
        if not all(_usable(point) for point in required):
            continue
        art_length = _distance(art[start], art[end]) / art_torso
        ref_length = _distance(ref[start], ref[end]) / ref_torso
        relative = abs(art_length - ref_length) / max(ref_length, 1e-6)
        if relative > 0.24 * scale:
            direction = "longer" if art_length > ref_length else "shorter"
            findings.append(
                PoseFinding(
                    status="suspicious",
                    category="proportion",
                    title=f"{label.title()} differs from the reference",
                    observation=f"Artwork normalized length: {art_length:.2f} torso units",
                    reference=f"Reference normalized length: {ref_length:.2f} torso units",
                    difference=f"{relative * 100:.0f}% {direction}",
                    keypoints=[start, end],
                    confidence=_confidence(*required),
                    suggestion=f"Move the {end.replace('_', ' ')} toward the reference direction, then re-check the silhouette.",
                )
            )

    for label, (start, joint, end) in JOINTS.items():
        required = (
            art[start], art[joint], art[end],
            ref[start], ref[joint], ref[end],
        )
        if not all(_usable(point) for point in required):
            continue
        art_angle = _angle(art[start], art[joint], art[end])
        ref_angle = _angle(ref[start], ref[joint], ref[end])
        delta = abs(art_angle - ref_angle)
        if delta > 18 * scale:
            findings.append(
                PoseFinding(
                    status="suspicious",
                    category="angle",
                    title=f"{label.title()} bend differs from the reference",
                    observation=f"Artwork joint angle: {art_angle:.1f}°",
                    reference=f"Reference joint angle: {ref_angle:.1f}°",
                    difference=f"{delta:.1f}°",
                    keypoints=[start, joint, end],
                    confidence=_confidence(*required),
                    suggestion=f"Adjust the {joint.replace('_', ' ')} or adjacent endpoint to match the intended bend.",
                )
            )

    # Shoulder/hip counter-tilt is a compact check for the action's main axes.
    for label, left, right in (
        ("shoulder axis", "left_shoulder", "right_shoulder"),
        ("hip axis", "left_hip", "right_hip"),
    ):
        required = (art[left], art[right], ref[left], ref[right])
        if not all(_usable(point) for point in required):
            continue
        art_axis = math.degrees(math.atan2(art[right].y - art[left].y, art[right].x - art[left].x))
        ref_axis = math.degrees(math.atan2(ref[right].y - ref[left].y, ref[right].x - ref[left].x))
        delta = abs((art_axis - ref_axis + 90) % 180 - 90)
        if delta > 13 * scale:
            findings.append(
                PoseFinding(
                    status="suspicious",
                    category="alignment",
                    title=f"{label.title()} tilt differs from the reference",
                    observation=f"Artwork tilt: {art_axis:.1f}°",
                    reference=f"Reference tilt: {ref_axis:.1f}°",
                    difference=f"{delta:.1f}°",
                    keypoints=[left, right],
                    confidence=_confidence(*required),
                    suggestion=f"Rotate the {label} around its midpoint while preserving the intended gesture.",
                )
            )

    findings.sort(key=lambda item: (item.confidence, item.title), reverse=True)
    findings = findings[:8]
    if not findings:
        findings = [
            PoseFinding(
                status="consistent",
                category="evidence",
                title="No large 2D skeleton discrepancy found",
                observation="Comparable limb lengths, major joint bends, shoulder axis and hip axis stay within tolerance.",
                reference="The user-confirmed reference skeleton",
                difference="Within configured thresholds",
                keypoints=comparable,
                confidence=round(
                    sum(_confidence(art[name], ref[name]) for name in comparable)
                    / len(comparable),
                    3,
                ),
                suggestion="Inspect contour, volume and foreshortening separately; COCO-17 points cannot verify those properties.",
            )
        ]
    return PoseComparisonResult(
        overall_status="suspicious" if any(item.status == "suspicious" for item in findings) else "consistent",
        assumptions=assumptions,
        findings=findings,
        comparable_keypoint_count=len(comparable),
        tolerance_mode=style_mode,
    )
