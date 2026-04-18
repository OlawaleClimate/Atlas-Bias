import { NavLink, Route, Routes } from "react-router-dom";
import BrowseByBias from "./views/BrowseByBias";
import BrowseByModel from "./views/BrowseByModel";
import BrowseByParam from "./views/BrowseByParam";

export default function App() {
  const repoSlug = (import.meta.env.VITE_GITHUB_REPO || "").trim();
  const missingRepoConfig = repoSlug === "";

  return (
    <div className="app">
      <header className="topbar card">
        <div>
          <h1 style={{ margin: 0 }}>Climate Model Bias Atlas</h1>
          <p className="small" style={{ margin: "4px 0 0" }}>
            Causal map of biases, parameterization links, and fix histories.
          </p>
        </div>
        <nav className="nav">
          <NavLink to="/">By Bias</NavLink>
          <NavLink to="/models">By Model</NavLink>
          <NavLink to="/params">By Parameter</NavLink>
        </nav>
      </header>

      {missingRepoConfig && (
        <section className="config-banner card" role="status" aria-live="polite">
          <p style={{ margin: 0 }}>
            Feedback issue creation is not configured. Set VITE_GITHUB_REPO in your local .env file.
          </p>
          <a href="/setup.html" target="_blank" rel="noreferrer">
            Open setup instructions
          </a>
        </section>
      )}

      <Routes>
        <Route path="/" element={<BrowseByBias />} />
        <Route path="/models" element={<BrowseByModel />} />
        <Route path="/params" element={<BrowseByParam />} />
      </Routes>
    </div>
  );
}
