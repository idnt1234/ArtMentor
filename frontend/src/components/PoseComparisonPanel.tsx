import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, GitCompareArrows, LoaderCircle, Upload, X } from "lucide-react";
import { api, assetUrl } from "../api";
import type {
  PoseComparison,
  PoseSkeleton,
  PoseStyleMode,
  Project,
  Rect,
} from "../types";
import PoseCanvas from "./PoseCanvas";

const INITIAL_BOX: Rect = { x: 0.04, y: 0.03, width: 0.92, height: 0.94 };

interface Props {
  project: Project;
  onError: (message: string) => void;
}

export default function PoseComparisonPanel({ project, onError }: Props) {
  const [comparison, setComparison] = useState<PoseComparison | null>(null);
  const [reference, setReference] = useState<File | null>(null);
  const [styleMode, setStyleMode] = useState<PoseStyleMode>("semi_realistic");
  const [artworkBox, setArtworkBox] = useState<Rect>(INITIAL_BOX);
  const [referenceBox, setReferenceBox] = useState<Rect>(INITIAL_BOX);
  const [artworkSkeleton, setArtworkSkeleton] = useState<PoseSkeleton | null>(null);
  const [referenceSkeleton, setReferenceSkeleton] = useState<PoseSkeleton | null>(null);
  const [busy, setBusy] = useState<"upload" | "estimate" | "save" | "compare" | null>(null);

  const sync = (next: PoseComparison) => {
    setComparison(next);
    setStyleMode(next.style_mode);
    setArtworkSkeleton(next.artwork_skeleton ?? null);
    setReferenceSkeleton(next.reference_skeleton ?? null);
    if (next.artwork_skeleton) setArtworkBox(next.artwork_skeleton.bbox);
    if (next.reference_skeleton) setReferenceBox(next.reference_skeleton.bbox);
  };

  useEffect(() => {
    setComparison(null);
    setArtworkSkeleton(null);
    setReferenceSkeleton(null);
    api.latestPoseComparison(project.id)
      .then((next) => {
        if (next) sync(next);
      })
      .catch((cause: Error) => onError(cause.message));
  }, [project.id, onError]);

  const highlighted = useMemo(
    () => new Set(
      comparison?.result?.findings
        .filter((finding) => finding.status === "suspicious")
        .flatMap((finding) => finding.keypoints) ?? [],
    ),
    [comparison?.result],
  );

  const invalidateResult = () => {
    setComparison((current) =>
      current
        ? { ...current, status: "estimated", result: null }
        : current,
    );
  };

  const updateArtworkSkeleton = (next: PoseSkeleton) => {
    setArtworkSkeleton(next);
    invalidateResult();
  };

  const updateReferenceSkeleton = (next: PoseSkeleton) => {
    setReferenceSkeleton(next);
    invalidateResult();
  };

  const toggleVisibility = (
    skeleton: PoseSkeleton,
    update: (next: PoseSkeleton) => void,
    name: string,
  ) => {
    update({
      ...skeleton,
      confirmed: false,
      keypoints: skeleton.keypoints.map((point) =>
        point.name === name
          ? {
              ...point,
              visibility: point.visibility === "hidden" ? "visible" : "hidden",
              source: "user",
              confidence: 1,
            }
          : point,
      ),
    });
  };

  const create = async () => {
    if (!reference) return;
    setBusy("upload");
    try {
      sync(await api.createPoseComparison(project.id, reference, styleMode));
      setReference(null);
      setArtworkBox(INITIAL_BOX);
      setReferenceBox(INITIAL_BOX);
    } catch (cause) {
      onError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const estimate = async () => {
    if (!comparison) return;
    setBusy("estimate");
    try {
      sync(await api.estimatePose(comparison.id, artworkBox, referenceBox));
    } catch (cause) {
      onError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const save = async (confirm = false) => {
    if (!comparison || !artworkSkeleton || !referenceSkeleton) return null;
    setBusy(confirm ? "compare" : "save");
    try {
      const next = await api.updatePoseSkeletons(
        comparison.id,
        { ...artworkSkeleton, confirmed: confirm || artworkSkeleton.confirmed },
        { ...referenceSkeleton, confirmed: confirm || referenceSkeleton.confirmed },
      );
      sync(next);
      return next;
    } catch (cause) {
      onError((cause as Error).message);
      return null;
    } finally {
      if (!confirm) setBusy(null);
    }
  };

  const compare = async () => {
    const saved = await save(true);
    if (!saved) {
      setBusy(null);
      return;
    }
    try {
      sync(await api.comparePose(saved.id));
    } catch (cause) {
      onError((cause as Error).message);
    } finally {
      setBusy(null);
    }
  };

  if (!comparison) {
    return (
      <section className="pose-empty">
        <div className="pose-empty-icon"><GitCompareArrows size={28} /></div>
        <p className="eyebrow">Reference-based body check</p>
        <h2>Compare the drawing to a pose you trust.</h2>
        <p>
          This first version checks 2D joint placement, limb proportions and major joint
          angles. It will not claim that a stylized body is objectively wrong.
        </p>
        <label>
          <span>Reference photo or pose image</span>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={(event) => setReference(event.target.files?.[0] ?? null)}
          />
        </label>
        <label>
          <span>Tolerance</span>
          <select value={styleMode} onChange={(event) => setStyleMode(event.target.value as PoseStyleMode)}>
            <option value="realistic">Realistic</option>
            <option value="semi_realistic">Semi-realistic</option>
            <option value="stylized">Stylized</option>
            <option value="intentional_distortion">Intentional distortion</option>
          </select>
        </label>
        <button className="primary-action" disabled={!reference || busy !== null} onClick={create}>
          {busy === "upload" ? <LoaderCircle className="spin" size={18} /> : <Upload size={18} />}
          {reference ? `Use ${reference.name}` : "Choose a reference first"}
        </button>
      </section>
    );
  }

  return (
    <section className="pose-panel">
      <header className="pose-panel-header">
        <div>
          <p className="eyebrow">Reference-based body check</p>
          <h2>Confirm the evidence before comparing.</h2>
          <p>{comparison.reference_filename} · {styleMode.replaceAll("_", " ")} tolerance</p>
        </div>
        <span className={`pose-status ${comparison.status}`}>{comparison.status}</span>
      </header>

      <div className="pose-editor-grid">
        <article>
          <div className="pose-editor-title"><strong>Artwork</strong><small>{artworkSkeleton?.model || "Select one person"}</small></div>
          <PoseCanvas
            imageUrl={assetUrl(comparison.artwork_image_url)}
            bbox={artworkBox}
            onBboxChange={setArtworkBox}
            skeleton={artworkSkeleton}
            onSkeletonChange={updateArtworkSkeleton}
            highlighted={highlighted}
          />
          {artworkSkeleton && (
            <PointVisibility
              skeleton={artworkSkeleton}
              onToggle={(name) => toggleVisibility(artworkSkeleton, updateArtworkSkeleton, name)}
            />
          )}
        </article>
        <article>
          <div className="pose-editor-title"><strong>Reference</strong><small>{referenceSkeleton?.model || "Select the matching person"}</small></div>
          <PoseCanvas
            imageUrl={assetUrl(comparison.reference_image_url)}
            bbox={referenceBox}
            onBboxChange={setReferenceBox}
            skeleton={referenceSkeleton}
            onSkeletonChange={updateReferenceSkeleton}
            highlighted={highlighted}
          />
          {referenceSkeleton && (
            <PointVisibility
              skeleton={referenceSkeleton}
              onToggle={(name) => toggleVisibility(referenceSkeleton, updateReferenceSkeleton, name)}
            />
          )}
        </article>
      </div>

      {!artworkSkeleton || !referenceSkeleton ? (
        <div className="pose-actions">
          <p>Resize each orange box around exactly one matching figure.</p>
          <button className="primary-action" disabled={busy !== null} onClick={estimate}>
            {busy === "estimate" ? <LoaderCircle className="spin" size={18} /> : <GitCompareArrows size={18} />}
            Estimate both skeletons
          </button>
        </div>
      ) : (
        <>
          <div className="pose-warnings">
            {[...artworkSkeleton.warnings, ...referenceSkeleton.warnings]
              .filter((value, index, values) => values.indexOf(value) === index)
              .slice(0, 4)
              .map((warning) => <span key={warning}><AlertTriangle size={13} />{warning}</span>)}
          </div>
          <div className="pose-actions">
            <p>Drag misplaced joints. Yellow points were corrected by you; comparison uses the saved positions.</p>
            <button disabled={busy !== null} onClick={() => save(false)}>
              {busy === "save" ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}
              Save corrections
            </button>
            <button className="primary-action" disabled={busy !== null} onClick={compare}>
              {busy === "compare" ? <LoaderCircle className="spin" size={18} /> : <GitCompareArrows size={18} />}
              Confirm and compare
            </button>
          </div>
        </>
      )}

      {comparison.result && (
        <div className="pose-results">
          <div className={`pose-verdict ${comparison.result.overall_status}`}>
            {comparison.result.overall_status === "consistent" ? <Check size={18} /> : <AlertTriangle size={18} />}
            <div>
              <strong>{comparison.result.overall_status.replace("_", " ")}</strong>
              <small>{comparison.result.comparable_keypoint_count} comparable keypoints</small>
            </div>
          </div>
          <div className="pose-finding-grid">
            {comparison.result.findings.map((finding, index) => (
              <article key={`${finding.title}-${index}`} className={finding.status}>
                <div><span>{finding.category}</span><strong>{Math.round(finding.confidence * 100)}%</strong></div>
                <h3>{finding.title}</h3>
                <p>{finding.observation}</p>
                <p>{finding.reference}</p>
                <b>{finding.difference}</b>
                <small>{finding.suggestion}</small>
              </article>
            ))}
          </div>
          <details>
            <summary>Assumptions and limits</summary>
            {comparison.result.assumptions.map((assumption) => <p key={assumption}>• {assumption}</p>)}
          </details>
        </div>
      )}
      <button className="pose-new-reference" onClick={() => setComparison(null)}>
        <X size={14} /> Start with another reference
      </button>
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
      <summary>Point visibility · {lowCount} low confidence · {hiddenCount} hidden</summary>
      <div>
        {skeleton.keypoints.map((point) => (
          <button
            key={point.name}
            className={`${point.visibility === "hidden" ? "hidden" : ""} ${point.confidence < 0.3 ? "low" : ""}`}
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
