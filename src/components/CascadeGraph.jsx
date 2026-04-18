export default function CascadeGraph({ graph, selectedId }) {
  const links = (graph.edges || []).filter((edge) => !selectedId || edge.source === selectedId || edge.target === selectedId);
  if (!links.length) {
    return <p className="small">No cascade relationships for this selection.</p>;
  }

  return (
    <div className="list">
      {links.map((edge, idx) => (
        <div className="card" key={`${edge.source}-${edge.target}-${idx}`}>
          <strong>{edge.source}</strong> {edge.relationship} <strong>{edge.target}</strong>
          <div className="small">confidence: {edge.confidence}</div>
        </div>
      ))}
    </div>
  );
}
