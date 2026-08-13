import { useState } from "react";
import { GitCompareArrows, ScanLine } from "lucide-react";
import type { Project } from "../types";
import ArtworkPosePanel from "./ArtworkPosePanel";
import PoseComparisonPanel from "./PoseComparisonPanel";

interface Props {
  project: Project;
  onError: (message: string) => void;
}

export default function BodyCheckPanel({ project, onError }: Props) {
  const [mode, setMode] = useState<"artwork" | "reference">("artwork");

  return (
    <section className="body-check-shell">
      <nav className="body-check-modes" aria-label="Body check mode">
        <button
          type="button"
          className={mode === "artwork" ? "active" : ""}
          onClick={() => setMode("artwork")}
        >
          <ScanLine size={15} />
          Artwork self-check
          <small>No reference</small>
        </button>
        <button
          type="button"
          className={mode === "reference" ? "active" : ""}
          onClick={() => setMode("reference")}
        >
          <GitCompareArrows size={15} />
          Reference comparison
          <small>More precise</small>
        </button>
      </nav>
      {mode === "artwork" ? (
        <ArtworkPosePanel project={project} onError={onError} />
      ) : (
        <PoseComparisonPanel project={project} onError={onError} />
      )}
    </section>
  );
}
