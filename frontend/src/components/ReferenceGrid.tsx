import { ArrowUpRight } from "lucide-react";
import type { ReferenceItem } from "../types";

export default function ReferenceGrid({ references }: { references: ReferenceItem[] }) {
  return (
    <div className="reference-grid">
      {references.map((reference) => (
        <article className="reference-card" key={reference.id}>
          <a href={reference.source_url} target="_blank" rel="noreferrer" className="reference-image-wrap">
            <img src={reference.image_url} alt={reference.title} className="reference-image" />
            <span className="external-link"><ArrowUpRight size={15} /></span>
          </a>
          <div className="reference-copy">
            <p className="eyebrow">{reference.artist} · {reference.date}</p>
            <h4>{reference.title}</h4>
            <p>{reference.rationale}</p>
            <a href={reference.license_url} target="_blank" rel="noreferrer" className="license-link">
              {reference.license} ↗
            </a>
          </div>
        </article>
      ))}
    </div>
  );
}

