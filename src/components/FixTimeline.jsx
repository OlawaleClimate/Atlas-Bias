export default function FixTimeline({ attempts }) {
  if (!attempts || attempts.length === 0) {
    return <p className="small">No fix attempts documented yet.</p>;
  }

  return (
    <div className="list">
      {attempts.map((item, idx) => (
        <div className="card" key={`${item.model}-${idx}`}>
          <strong>{item.model} {item.version}</strong>
          <div className="small">change: {item.change}</div>
          <div className="small">mechanism: {item.mechanism}</div>
          <div className="small">outcome: {item.outcome}</div>
          <div className="small">side effects: {item.side_effects}</div>
        </div>
      ))}
    </div>
  );
}
