"""Conservative no-reference checks for one user-confirmed 2D skeleton."""

from __future__ import annotations

import math

from ..schemas import (
    PoseComparisonResult,
    PoseFinding,
    PoseKeypoint,
    PoseSkeleton,
    PoseStyleMode,
)

STYLE_SCALE: dict[PoseStyleMode, float] = {
    "realistic": 1.0,
    "semi_realistic": 1.2,
    "stylized": 1.55,
    "intentional_distortion": 2.1,
}
LIMBS = {
    "left arm": ("left_shoulder", "left_elbow", "left_wrist"),
    "right arm": ("right_shoulder", "right_elbow", "right_wrist"),
    "left leg": ("left_hip", "left_knee", "left_ankle"),
    "right leg": ("right_hip", "right_knee", "right_ankle"),
}
PAIRED_SEGMENTS = (
    ("upper arms", ("left_shoulder", "left_elbow"), ("right_shoulder", "right_elbow")),
    ("forearms", ("left_elbow", "left_wrist"), ("right_elbow", "right_wrist")),
    ("thighs", ("left_hip", "left_knee"), ("right_hip", "right_knee")),
    ("lower legs", ("left_knee", "left_ankle"), ("right_knee", "right_ankle")),
)


def _points(skeleton: PoseSkeleton) -> dict[str, PoseKeypoint]:
    return {point.name: point for point in skeleton.keypoints}


def _usable(point: PoseKeypoint) -> bool:
    return point.visibility != "hidden" and (
        point.source == "user" or point.confidence >= 0.3
    )


def _distance(a: PoseKeypoint, b: PoseKeypoint) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _confidence(*points: PoseKeypoint) -> float:
    return round(
        min(1.0 if point.source == "user" else point.confidence for point in points),
        3,
    )


def inspect_skeleton(
    skeleton: PoseSkeleton, style_mode: PoseStyleMode
) -> PoseComparisonResult:
    """Report only broad 2D inconsistencies that survive a style tolerance."""
    assumptions = [
        "There is no reference image; findings indicate unusual 2D geometry, not anatomical proof.",
        "Strong foreshortening, hidden joints and perspective can explain left-right length differences.",
        f"Tolerance uses the {style_mode.replace('_', ' ')} profile.",
    ]
    if not skeleton.confirmed:
        return PoseComparisonResult(
            overall_status="insufficient",
            assumptions=assumptions,
            findings=[
                PoseFinding(
                    status="insufficient",
                    category="evidence",
                    title="Confirm the artwork skeleton first",
                    observation="The detected joints have not been checked by the artist.",
                    reference="A user-confirmed COCO-17 skeleton",
                    difference="Self-check not run",
                    confidence=1,
                    suggestion="Drag misplaced joints, mark hidden points, then confirm the skeleton.",
                )
            ],
            comparable_keypoint_count=0,
            tolerance_mode=style_mode,
        )

    points = _points(skeleton)
    usable = [name for name, point in points.items() if _usable(point)]
    if len(usable) < 10:
        return PoseComparisonResult(
            overall_status="insufficient",
            assumptions=assumptions,
            findings=[
                PoseFinding(
                    status="insufficient",
                    category="evidence",
                    title="Too few reliable joints",
                    observation=f"Only {len(usable)} of 17 points are available.",
                    reference="At least 10 visible or user-corrected points",
                    difference=f"{10 - len(usable)} points missing",
                    keypoints=usable,
                    confidence=0.95,
                    suggestion="Correct uncertain joints or mark genuinely hidden joints before retrying.",
                )
            ],
            comparable_keypoint_count=len(usable),
            tolerance_mode=style_mode,
        )

    scale = STYLE_SCALE[style_mode]
    findings: list[PoseFinding] = []

    # Within-limb segment ratios catch a misplaced elbow/knee without assuming a
    # universal body canon. The range is intentionally broad for 2D projection.
    for label, (root, joint, end) in LIMBS.items():
        required = (points[root], points[joint], points[end])
        if not all(_usable(point) for point in required):
            continue
        first = _distance(points[root], points[joint])
        second = _distance(points[joint], points[end])
        ratio = second / max(first, 1e-6)
        lower = 0.48 / scale
        upper = 1.62 * scale
        if ratio < lower or ratio > upper:
            direction = "long" if ratio > upper else "short"
            findings.append(
                PoseFinding(
                    status="suspicious",
                    category="proportion",
                    title=f"{label.title()} segment ratio is unusual",
                    observation=f"Outer/inner segment ratio: {ratio:.2f}",
                    reference=f"Broad 2D tolerance under this style: {lower:.2f}–{upper:.2f}",
                    difference=f"Outer segment appears relatively {direction}",
                    keypoints=[root, joint, end],
                    confidence=_confidence(*required),
                    suggestion=f"Recheck the {joint.replace('_', ' ')} position before changing the contour.",
                )
            )

    # Left-right asymmetry is evidence only when it is very large. The copy
    # explicitly calls out foreshortening rather than labeling it an error.
    for label, left_names, right_names in PAIRED_SEGMENTS:
        required = tuple(points[name] for name in (*left_names, *right_names))
        if not all(_usable(point) for point in required):
            continue
        left = _distance(points[left_names[0]], points[left_names[1]])
        right = _distance(points[right_names[0]], points[right_names[1]])
        ratio = max(left, right) / max(min(left, right), 1e-6)
        threshold = 1.75 * scale
        if ratio > threshold:
            shorter_side = "left" if left < right else "right"
            findings.append(
                PoseFinding(
                    status="suspicious",
                    category="proportion",
                    title=f"Projected {label} differ strongly",
                    observation=f"Longer/shorter projected length ratio: {ratio:.2f}",
                    reference=f"Review threshold for this style: {threshold:.2f}",
                    difference=f"The {shorter_side} side is much shorter in 2D",
                    keypoints=[*left_names, *right_names],
                    confidence=_confidence(*required),
                    suggestion="If this is not strong foreshortening, move the shorter side's middle or end joint and recheck.",
                )
            )

    # A hip center far beyond both visible ankles often means the weight/support
    # relationship deserves review, but dynamic motion can intentionally do this.
    balance_points = (
        points["left_hip"],
        points["right_hip"],
        points["left_ankle"],
        points["right_ankle"],
    )
    if all(_usable(point) for point in balance_points):
        hip_x = (points["left_hip"].x + points["right_hip"].x) / 2
        left_x = points["left_ankle"].x
        right_x = points["right_ankle"].x
        support_min, support_max = sorted((left_x, right_x))
        margin = max((support_max - support_min) * 0.35 * scale, 0.025)
        if hip_x < support_min - margin or hip_x > support_max + margin:
            side = "left" if hip_x < support_min else "right"
            offset = support_min - hip_x if side == "left" else hip_x - support_max
            findings.append(
                PoseFinding(
                    status="suspicious",
                    category="alignment",
                    title="Hip center falls outside the visible support span",
                    observation=f"Hip center sits {offset:.3f} image widths beyond the {side} ankle span.",
                    reference="Static balance usually projects between or near the supporting feet.",
                    difference=f"Weight projects to the {side}",
                    keypoints=["left_hip", "right_hip", "left_ankle", "right_ankle"],
                    confidence=_confidence(*balance_points),
                    suggestion="If the pose is not falling or stepping, recheck the hip and ankle positions before redrawing the silhouette.",
                )
            )

    findings.sort(key=lambda finding: (finding.confidence, finding.title), reverse=True)
    findings = findings[:8]
    if not findings:
        findings = [
            PoseFinding(
                status="consistent",
                category="evidence",
                title="No large 2D skeleton inconsistency found",
                observation="Segment ratios, strong left-right differences and visible support alignment stay within broad tolerance.",
                reference="Conservative no-reference checks",
                difference="Within configured thresholds",
                keypoints=usable,
                confidence=round(
                    sum(_confidence(points[name]) for name in usable) / len(usable),
                    3,
                ),
                suggestion="Continue with volume, contour and foreshortening checks; COCO-17 joints cannot verify those properties.",
            )
        ]
    return PoseComparisonResult(
        overall_status=(
            "suspicious"
            if any(finding.status == "suspicious" for finding in findings)
            else "consistent"
        ),
        assumptions=assumptions,
        findings=findings,
        comparable_keypoint_count=len(usable),
        tolerance_mode=style_mode,
    )
