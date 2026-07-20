import { useState } from "react";
import type { ComparisonResult } from "../types";

interface Props {
  beforeUrl: string;
  afterUrl: string;
  comparison: ComparisonResult;
}

export default function RevisionCompare({ beforeUrl, afterUrl, comparison }: Props) {
  const [position, setPosition] = useState(50);
  return (
    <section className="revision-report">
      <div className="compare-frame">
        <img src={beforeUrl} alt="Original artwork" />
        <div className="after-layer" style={{ width: `${position}%` }}>
          <img src={afterUrl} alt="Revised artwork" />
        </div>
        <div className="compare-line" style={{ left: `${position}%` }} />
        <input
          aria-label="Compare before and after"
          type="range"
          min="0"
          max="100"
          value={position}
          onChange={(event) => setPosition(Number(event.target.value))}
        />
        <span className="compare-label before">Before</span>
        <span className="compare-label after">After</span>
      </div>
      <div className="comparison-copy">
        <p className="report-summary">{comparison.summary}</p>
        <div className="change-grid">
          {comparison.changes.map((change) => (
            <article key={change.dimension}>
              <span className={`outcome ${change.outcome}`}>{change.outcome}</span>
              <h4>{change.dimension}</h4>
              <p>{change.explanation}</p>
              <small>{change.evidence}</small>
            </article>
          ))}
        </div>
        <div className="next-step"><span>Next step</span>{comparison.next_step}</div>
      </div>
    </section>
  );
}

