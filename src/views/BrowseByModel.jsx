import { useMemo, useState } from "react";
import { loadBiasEntries } from "../data/loader";
import { models } from "../data/models";

export default function BrowseByModel() {
  const entries = useMemo(() => loadBiasEntries(), []);
  const [model, setModel] = useState(models[0]?.id || "");

  const linked = entries.filter((item) => Object.prototype.hasOwnProperty.call(item.severity_by_model || {}, model));

  return (
    <div className="grid">
      <section className="card">
        <h2 style={{ marginTop: 0 }}>Browse by Model</h2>
        <select value={model} onChange={(event) => setModel(event.target.value)}>
          {models.map((m) => (
            <option key={m.id} value={m.id}>{m.id}</option>
          ))}
        </select>
        <p className="small">Biases linked to selected model through severity_by_model.</p>
      </section>

      <section className="list">
        {linked.map((item) => (
          <article className="card" key={item.id}>
            <h3 style={{ marginTop: 0 }}>{item.name}</h3>
            <p>{item.description}</p>
            <div className="small">severity: {item.severity_by_model[model]?.severity}</div>
            <div className="small">direction: {item.severity_by_model[model]?.direction}</div>
            <div className="small">source: {item.severity_by_model[model]?.source}</div>
          </article>
        ))}
      </section>
    </div>
  );
}
