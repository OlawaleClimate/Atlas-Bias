import GenerationBadge from "./GenerationBadge";
import ModelSeverityBar from "./ModelSeverityBar";
import FixTimeline from "./FixTimeline";

/** Parse a description string and replace [N] with superscript anchor links. */
function DescriptionWithCitations({ text }) {
  if (!text) return null;
  // Split on [N] markers, keeping the captured group
  const parts = text.split(/(\[\d+\])/);
  return (
    <>
      {parts.map((part, i) => {
        const match = part.match(/^\[(\d+)\]$/);
        if (match) {
          const n = match[1];
          return (
            <sup key={i}>
              <a
                href={`#cite-${n}`}
                style={{ color: "var(--accent)", textDecoration: "none", fontFamily: "var(--mono)", fontSize: "11px" }}
              >
                [{n}]
              </a>
            </sup>
          );
        }
        // Preserve paragraph breaks
        return part.split("\n\n").map((para, j) =>
          j === 0 ? <span key={`${i}-${j}`}>{para}</span> : <><br key={`br1-${i}-${j}`}/><br key={`br2-${i}-${j}`}/><span key={`${i}-${j}`}>{para}</span></>
        );
      })}
    </>
  );
}

export default function BiasCard({ bias }) {
  if (!bias) {
    return <div className="card">Select a bias entry to inspect details.</div>;
  }

  return (
    <div className="grid" style={{ gap: "14px" }}>
      <section className="card">
        <h2 style={{ marginTop: 0 }}>{bias.name}</h2>
        <div className="small">id: {bias.id}</div>
        <div className="small">region: {bias.region} | season: {bias.season}</div>
        <div className="small">persistence: {bias.persistence}</div>
        <p style={{ lineHeight: 1.7 }}>
          <DescriptionWithCitations text={bias.description} />
        </p>
      </section>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>CMIP History</h3>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          {(bias.cmip_history || []).map((item) => (
            <GenerationBadge key={`${item.generation}-${item.severity}`} generation={item.generation} severity={item.severity} />
          ))}
        </div>
      </section>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>Model Severity</h3>
        <ModelSeverityBar severityByModel={bias.severity_by_model} />
      </section>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>Fix Attempts</h3>
        <FixTimeline attempts={bias.fix_attempts} />
      </section>

      {(bias.citations || []).length > 0 && (
        <section className="card">
          <h3 style={{ marginTop: 0 }}>References</h3>
          <ol style={{ margin: 0, paddingLeft: "1.4em", display: "grid", gap: "12px" }}>
            {bias.citations.map((c, i) => (
              <li key={c.doi} id={`cite-${i + 1}`} style={{ fontSize: "13px", lineHeight: 1.6 }}>
                <div style={{ fontWeight: 600, marginBottom: "2px" }}>
                  {c.title || <em style={{ color: "var(--muted)" }}>Title unavailable</em>}
                </div>
                <span style={{ color: "var(--muted)" }}>{c.authors} ({c.year}). </span>
                <em>{c.journal}.</em>{" "}
                <a
                  href={`https://doi.org/${c.doi}`}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: "var(--accent)", fontFamily: "var(--mono)", fontSize: "12px" }}
                >
                  {c.doi}
                </a>
                <div className="small" style={{ marginTop: "4px", color: "var(--muted)" }}>
                  {c.relevance}
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}
