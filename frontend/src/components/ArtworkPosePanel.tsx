import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  LoaderCircle,
  RefreshCw,
  Save,
  ScanLine,
} from "lucide-react";
import { api, assetUrl } from "../api";
import type {
  PoseInspection,
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

export default function ArtworkPosePanel({ project, onError }: Props) {
  const [inspection, setInspection] = useState<PoseInspection | null>(null);
  const [skeleton, setSkeleton] = useState<PoseSkeleton | null>(null);
  const [bbox, setBbox] = useState<Rect>(INITIAL_BOX);
  const [styleMode, setStyleMode] =
    useState<PoseStyleMode>("semi_realistic");
  const [busy, setBusy] =
    useState<"load" | "estimate" | "save" | "check" | null>("load");

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
