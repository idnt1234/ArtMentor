import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Box,
  Check,
  LoaderCircle,
  RefreshCw,
  Save,
  ScanLine,
} from "lucide-react";
import { api, assetUrl } from "../api";
import type {
  PoseInspection,
  Pose3DReconstruction,
  PoseSkeleton,
  PoseStyleMode,
  Project,
  Rect,
} from "../types";
import PoseCanvas from "./PoseCanvas";

const INITIAL_BOX: Rect = { x: 0.01, y: 0.01, width: 0.98, height: 0.98 };
const pendingLoads = new Map<string, Promise<PoseInspection>>();

interface Props {
  project: Project;
  pose3dEnabled: boolean;
  onError: (message: string) => void;
}

function loadOrEstimate(projectId: string): Promise<PoseInspection> {
  const active = pendingLoads.get(projectId);
  if (active) return active;
  const request = api
    .poseInspection(projectId)
    .then((saved) =>
      saved
        ?? api.estimatePoseInspection(projectId, INITIAL_BOX, "semi_realistic"),
    )
    .finally(() => pendingLoads.delete(projectId));
  pendingLoads.set(projectId, request);
  return request;
}

export default function ArtworkPosePanel({ project, pose3dEnabled, onError }: Props) {
  const [inspection, setInspection] = useState<PoseInspection | null>(null);
  const [preview3d, setPreview3d] = useState<Pose3DReconstruction | null>(null);
  const [skeleton, setSkeleton] = useState<PoseSkeleton | null>(null);
  const [bbox, setBbox] = useState<Rect>(INITIAL_BOX);
  const [styleMode, setStyleMode] =
    useState<PoseStyleMode>("semi_realistic");
  const [busy, setBusy] =
    useState<"load" | "estimate" | "save" | "check" | "pose3d" | null>("load");

  const sync = (next: PoseInspection) => {
    setInspection(next);
    setSkeleton(next.skeleton);
    setBbox(next.skeleton.bbox);
    setStyleMode(next.style_mode);
  };

  useEffect(() => {
    let active = true;
    setInspection(null);
    setSkeleton(null);
    setBusy("load");
    loadOrEstimate(project.id)
      .then((next) => {
        if (active) sync(next);
      })
      .catch((cause: Error) => {
        if (active) onError(cause.message);
      })
      .finally(() => {
        if (active) setBusy(null);
      });
    return () => {
      active = false;
    };
  }, [project.id, onError]);

  useEffect(() => {
    if (!pose3dEnabled) {
      setPreview3d(null);
      return;
    }
    let active = true;
    api.latestPose3D(project.id)
      .then((saved) => {
        if (active) setPreview3d(saved);
      })
      .catch((cause: Error) => {
        if (active) onError(cause.message);
      });
    return () => {
      active = false;
    };
  }, [project.id, pose3dEnabled, onError]);

  const highlighted = useMemo(
    () =>
      new Set(
        inspection?.result?.findings
          .filter((finding) => finding.status === "suspicious")
          .flatMap((finding) => finding.keypoints) ?? [],
      ),
    [inspection?.result],
  );

  const updateSkeleton = (next: PoseSkeleton) => {
    setSkeleton(next);
    setPreview3d((current) => current ? { ...current, stale: true } : current);
    setInspection((current) =>
      current ? { ...current, status: "estimated", result: null } : current,
    );
  };

  const toggleVisibility = (name: string) => {
    if (!skeleton) return;
    updateSkeleton({
      ...skeleton,
      confirmed: false,
      keypoints: skeleton.keypoints.map((point) =>
        point.name === name
          ? {
              ...point,
              visibility:
                point.visibility === "hidden" ? "visible" : "hidden",
              source: "user",
              confidence: 1,
            }
          : point,
      ),
    });
  };

  const estimate = async () => {
    setBusy("estimate");
    try {
      sync(await api.estimatePoseInspection(project.id, bbox, styleMode));
    } catch (cause) {
      onError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const save = async (confirm = false) => {
    if (!skeleton) return null;
    setBusy(confirm ? "check" : "save");
    try {
      const next = await api.updatePoseInspection(project.id, {
        ...skeleton,
        confirmed: confirm || skeleton.confirmed,
      });
      sync(next);
      return next;
    } catch (cause) {
      onError((cause as Error).message);
      return null;
    } finally {
      if (!confirm) setBusy(null);
    }
  };

  const check = async () => {
    const saved = await save(true);
    if (!saved) {
      setBusy(null);
      return;
    }
    try {
      sync(await api.checkPoseInspection(project.id));
    } catch (cause) {
      onError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const reconstruct3d = async () => {
    if (!skeleton?.confirmed) return;
    setBusy("pose3d");
    try {
      setPreview3d(await api.reconstructPose3D(project.id));
    } catch (cause) {
      onError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  };

  if (busy === "load" && !inspection) {
    return (
      <div className="pose-autoload">
        <LoaderCircle className="spin" size={26} />
        <div>
          <strong>Extracting an editable skeleton locally…</strong>
          <p>This is the actual RTMPose body-check pipeline, not the critique model.</p>
        </div>
      </div>
    );
  }

  return (
    <section className="pose-panel artwork-pose-panel">
      <header className="pose-panel-header">
        <div>
          <p className="eyebrow">No-reference artwork self-check</p>
          <h2>Correct the skeleton, then check its 2D structure.</h2>
          <p>
            Blue is model output; yellow is your correction. No conclusion is
            generated until you confirm these joints.
          </p>
        </div>
        <span className={`pose-status ${inspection?.status ?? "estimated"}`}>
          {inspection?.status ?? "not estimated"}
        </span>
      </header>

      <div className="pose-scope-note">
        <AlertTriangle size={16} />
        <div>
          <strong>This does not prove anatomy is right or wrong.</strong>
          <p>
            Without a reference, it only flags unusually large 2D joint and
            proportion relationships under the selected style tolerance.
          </p>
        </div>
      </div>

      <div className="artwork-pose-editor">
        <article>
          <div className="pose-editor-title">
            <strong>Your artwork + editable COCO-17 skeleton</strong>
            <small>{skeleton?.model || "Frame one figure"}</small>
          </div>
          <PoseCanvas
            imageUrl={assetUrl(project.image_url)}
            bbox={bbox}
            onBboxChange={setBbox}
            skeleton={skeleton}
            onSkeletonChange={updateSkeleton}
            highlighted={highlighted}
            fitToImage
          />
          {skeleton && (
            <PointVisibility
              skeleton={skeleton}
              onToggle={toggleVisibility}
            />
          )}
        </article>
        <aside className="pose-evidence-guide">
          <span className="pose-step-index">01</span>
          <h3>Verify the detected joints</h3>
          <p>
            Put shoulders, elbows, wrists, hips, knees and ankles on the intended
            joint centers—not on clothing edges.
          </p>
          <ul>
            <li><i className="model-dot" /> White/blue: RTMPose estimate</li>
            <li><i className="user-dot" /> Yellow: manually corrected</li>
            <li><i className="warning-dot" /> Red: involved in a finding</li>
          </ul>
          <label>
            <span>Style tolerance</span>
            <select
              value={styleMode}
              disabled={Boolean(skeleton)}
              onChange={(event) =>
                setStyleMode(event.target.value as PoseStyleMode)
              }
            >
              <option value="realistic">Realistic</option>
              <option value="semi_realistic">Semi-realistic</option>
              <option value="stylized">Stylized</option>
              <option value="intentional_distortion">Intentional distortion</option>
            </select>
            {skeleton && <small>Reframe to change tolerance and rerun.</small>}
          </label>
        </aside>
      </div>

      {!skeleton ? (
        <div className="pose-actions">
          <p>Resize the orange box around one complete person.</p>
          <button
            className="primary-action"
            disabled={busy !== null}
            onClick={estimate}
          >
            {busy === "estimate" ? (
              <LoaderCircle className="spin" size={18} />
            ) : (
              <ScanLine size={18} />
            )}
            Detect skeleton
          </button>
        </div>
      ) : (
        <>
          <div className="pose-warnings">
            {skeleton.warnings.slice(0, 4).map((warning) => (
              <span key={warning}>
                <AlertTriangle size={13} />
                {warning}
              </span>
            ))}
          </div>
          <div className="pose-actions">
            <p>
              Drag incorrect joints and mark hidden joints. Checking uses exactly
              the points shown here.
            </p>
            <button
              disabled={busy !== null}
              onClick={() => {
                setSkeleton(null);
                setInspection((current) =>
                  current
                    ? { ...current, status: "estimated", result: null }
                    : current,
                );
              }}
            >
              <RefreshCw size={16} />
              Reframe person
            </button>
            <button disabled={busy !== null} onClick={() => save(false)}>
              {busy === "save" ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <Save size={16} />
              )}
              Save corrections
            </button>
            <button
              className="primary-action"
              disabled={busy !== null}
              onClick={check}
            >
              {busy === "check" ? (
                <LoaderCircle className="spin" size={18} />
              ) : (
                <Check size={18} />
              )}
              Confirm skeleton and check
            </button>
          </div>
        </>
      )}

      {inspection?.result && (
        <div className="pose-results">
          <div className={`pose-verdict ${inspection.result.overall_status}`}>
            {inspection.result.overall_status === "consistent" ? (
              <Check size={18} />
            ) : (
              <AlertTriangle size={18} />
            )}
            <div>
              <strong>{inspection.result.overall_status}</strong>
              <small>
                {inspection.result.comparable_keypoint_count} evidence points
              </small>
            </div>
          </div>
          <div className="pose-finding-grid">
            {inspection.result.findings.map((finding, index) => (
              <article
                key={`${finding.title}-${index}`}
                className={finding.status}
              >
                <div>
                  <span>{finding.category}</span>
                  <strong>{Math.round(finding.confidence * 100)}%</strong>
                </div>
                <h3>{finding.title}</h3>
                <p><span className="evidence-label">Observed</span> {finding.observation}</p>
                <p><span className="evidence-label">Threshold</span> {finding.reference}</p>
                <em>{finding.difference}</em>
                <small>{finding.suggestion}</small>
              </article>
            ))}
          </div>
          <details open>
            <summary>Assumptions and limits</summary>
            {inspection.result.assumptions.map((assumption) => (
              <p key={assumption}>• {assumption}</p>
            ))}
          </details>
        </div>
      )}

      {pose3dEnabled && skeleton && (
        <section className="pose3d-preview">
          <header>
            <div className="pose3d-mark"><Box size={19} /></div>
            <div>
              <p className="eyebrow">Private research beta</p>
              <h2>Single-image 3D hypothesis</h2>
              <p>
                SAM 3D Body turns the confirmed 2D evidence into one possible
                mesh. Side and top views reveal depth assumptions that the
                original image cannot verify.
              </p>
            </div>
            <button
              type="button"
              className="primary-action"
              disabled={busy !== null || !skeleton.confirmed}
              onClick={reconstruct3d}
            >
              {busy === "pose3d" ? (
                <LoaderCircle className="spin" size={17} />
              ) : (
                <Box size={16} />
              )}
              {preview3d ? "Regenerate from current skeleton" : "Generate 3D preview"}
            </button>
          </header>

          {!skeleton.confirmed && (
            <div className="pose3d-gate">
              Confirm the editable 2D skeleton first. The 3D worker never runs
              from unreviewed model points.
            </div>
          )}

          {preview3d && (
            <>
              {preview3d.stale && (
                <div className="pose3d-stale">
                  <AlertTriangle size={15} /> This preview belongs to an older
                  skeleton. Confirm your edits and regenerate it.
                </div>
              )}
              <div className="pose3d-view-grid">
                <figure className="pose3d-overlay">
                  <img src={assetUrl(preview3d.overlay_image_url)} alt="Confirmed 2D points compared with the projected 3D hypothesis" />
                  <figcaption>2D evidence overlay</figcaption>
                </figure>
                <figure>
                  <img src={assetUrl(preview3d.camera_image_url)} alt="Camera view of the reconstructed 3D mesh" />
                  <figcaption>Camera view</figcaption>
                </figure>
                <figure>
                  <img src={assetUrl(preview3d.side_image_url)} alt="Side view of the reconstructed 3D mesh" />
                  <figcaption>Side hypothesis</figcaption>
                </figure>
                <figure>
                  <img src={assetUrl(preview3d.top_image_url)} alt="Top view of the reconstructed 3D mesh" />
                  <figcaption>Top hypothesis</figcaption>
                </figure>
              </div>
              <div className="pose3d-evidence">
                <div>
                  <span>2D projection error</span>
                  <strong>
                    {preview3d.result.metrics.mean_projection_error_normalized == null
                      ? "insufficient evidence"
                      : `${(preview3d.result.metrics.mean_projection_error_normalized * 100).toFixed(2)}% of person-box diagonal`}
                  </strong>
                </div>
                <div>
                  <span>Reviewed joints</span>
                  <strong>{preview3d.result.metrics.reviewed_keypoint_count} / 17</strong>
                </div>
                <div>
                  <span>2D prompts used</span>
                  <strong>
                    {preview3d.result.prompted_joints.length
                      ? preview3d.result.prompted_joints.map((name) => name.replaceAll("_", " ")).join(", ")
                      : "box only"}
                  </strong>
                </div>
                <div>
                  <span>GPU inference</span>
                  <strong>{preview3d.result.inference_seconds.toFixed(2)} s</strong>
                </div>
              </div>
              <details className="pose3d-limits" open>
                <summary>What this preview can and cannot say</summary>
                {preview3d.result.limitations.map((limit) => <p key={limit}>• {limit}</p>)}
              </details>
            </>
          )}
        </section>
      )}
    </section>
  );
}

function PointVisibility({
  skeleton,
  onToggle,
}: {
  skeleton: PoseSkeleton;
  onToggle: (name: string) => void;
}) {
  const lowCount = skeleton.keypoints.filter(
    (point) => point.source === "model" && point.confidence < 0.3,
  ).length;
  const hiddenCount = skeleton.keypoints.filter(
    (point) => point.visibility === "hidden",
  ).length;
  return (
    <details className="pose-point-list">
      <summary>
        Point visibility · {lowCount} low confidence · {hiddenCount} hidden
      </summary>
      <div>
        {skeleton.keypoints.map((point) => (
          <button
            key={point.name}
            className={`${point.visibility === "hidden" ? "hidden" : ""} ${
              point.confidence < 0.3 ? "low" : ""
            }`}
            onClick={() => onToggle(point.name)}
            type="button"
          >
            {point.name.replaceAll("_", " ")}
          </button>
        ))}
      </div>
    </details>
  );
}
