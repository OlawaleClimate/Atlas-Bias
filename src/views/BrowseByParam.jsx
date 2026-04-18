import { useMemo, useState } from "react";
import { loadBiasEntries } from "../data/loader";

export default function BrowseByParam() {
  const entries = useMemo(() => loadBiasEntries(), []);
  const [param, setParam] = useState("cape_threshold_J_kg");

  const linked = entries.filter((item) =>
    (item.implicated_params || []).some((p) => p.parameter.toLowerCase().includes(param.toLowerCase()))
  );

  return (
    <div className="grid">
      <section className="card">
        <h2 style={{ marginTop: 0 }}>Browse by Parameter</h2>
        <input value={param} onChange={(event) => setParam(event.target.value)} />
        <p className="small">Shared namespace with Config Comparison App appears here.</p>
      </section>

      <section className="list">
        {linked.map((item) => (
          <article className="card" key={item.id}>
            <h3 style={{ marginTop: 0 }}>{item.name}</h3>
            {(item.implicated_params || [])
              .filter((p) => p.parameter.toLowerCase().includes(param.toLowerCase()))
              .map((p, idx) => (
                <div className="small" key={`${item.id}-${idx}`}>
                  {p.subsystem}.{p.parameter} ({p.type}) - {p.role}
                </div>
              ))}
          </article>
        ))}
      </section>
    </div>
  );
}
