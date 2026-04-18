export default function ModelSeverityBar({ severityByModel }) {
  const rows = Object.entries(severityByModel || {});
  if (!rows.length) {
    return <p className="small">No model severity mapping yet.</p>;
  }

  return (
    <div className="list">
      {rows.map(([model, meta]) => (
        <div className="card" key={model}>
          <strong>{model}</strong>
          <div className="small">severity: {meta.severity}</div>
          <div className="small">direction: {meta.direction}</div>
          <div className="small">source: {meta.source}</div>
        </div>
      ))}
    </div>
  );
}
