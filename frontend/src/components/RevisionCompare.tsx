import { useLocale } from "../i18n";
import { useState } from "react";
import type { ComparisonResult } from "../types";

interface Props {
  beforeUrl: string;
  afterUrl: string;
  comparison: ComparisonResult;
}

export default function RevisionCompare({ beforeUrl, afterUrl, comparison }: Props) {
  const { t } = useLocale();
  const [position, setPosition] = useState(50);
  return (
    <section className="revision-report">
      <div className="compare-frame">
        <img src={beforeUrl} alt={t("Original artwork")} />
        <div className="after-layer" style={{ width: `${position}%` }}>
          <img src={afterUrl} alt={t("Revised artwork")} />
        </div>
        <div className="compare-line" style={{ left: `${position}%` }} />
        <input
          aria-label={t("Compare before and after")}
          type="range"
          min="0"
          max="100"
          value={position}
          onChange={(event) => setPosition(Number(event.target.value))}
        />
        <span className="compare-label before">{t("Before")}</span>
        <span className="compare-label after">{t("After")}</span>
      </div>
      <div className="comparison-copy">
        <p className="report-summary">{comparison.summary}</p>
        <div className="change-grid">
          {comparison.changes.map((change) => (
            <article key={change.dimension}>
              <span className={`outcome ${change.outcome}`}>{t(change.outcome)}</span>
              <h4>{t(change.dimension)}</h4>
              <p>{change.explanation}</p>
              <small>{change.evidence}</small>
            </article>
          ))}
        </div>
        <div className="next-step"><span>{t("Next step")}</span>{comparison.next_step}</div>
      </div>
    </section>
  );
}

