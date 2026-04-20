import { useMemo, useState } from "react";
import BiasCard from "../components/BiasCard";
import CascadeGraph from "../components/CascadeGraph";
import FeedbackForm from "../components/FeedbackForm";
import ReviewQueue from "../components/ReviewQueue";
import { loadBiasEntries } from "../data/loader";
import cascadeGraph from "../data/cascade_graph.json";

export default function BrowseByBias() {
  const entries = useMemo(() => loadBiasEntries(), []);
  const [selectedId, setSelectedId] = useState(entries[0]?.id || "");

  const filtered = entries;
  const selected = filtered.find((item) => item.id === selectedId) || null;

  return (
    <div className="grid grid-2">
      <section className="card list">
        <h3 style={{ marginTop: 0 }}>Bias Entries</h3>
        {filtered.map((item) => (
          <button
            key={item.id}
            onClick={() => setSelectedId(item.id)}
            className={item.id === selectedId ? "list-btn selected" : "list-btn"}
          >
            {item.name}
          </button>
        ))}
      </section>

      <section className="grid">
        <BiasCard bias={selected} />
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Cascade Graph</h3>
          <CascadeGraph graph={cascadeGraph} selectedId={selected?.id} />
        </div>
        <FeedbackForm selectedBias={selected} />
        <ReviewQueue />
      </section>
    </div>
  );
}
