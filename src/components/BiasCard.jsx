import GenerationBadge from "./GenerationBadge";
import ModelSeverityBar from "./ModelSeverityBar";
import FixTimeline from "./FixTimeline";

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
        <p>{bias.description}</p>
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
    </div>
  );
}
