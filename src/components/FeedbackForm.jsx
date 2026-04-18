import { useMemo, useState } from "react";

const DEFAULT_REPO = import.meta.env.VITE_GITHUB_REPO || "";
const DOI_PATTERN = /^10\.\d{4,9}\/\S+$/i;

function buildIssueBody({ biasId, feedbackType, fieldName, correction, doi, verdict, confidence }) {
  return [
    `bias_id: ${biasId}`,
    `verdict: ${verdict}`,
    `confidence: ${confidence}`,
    `doi: ${doi}`,
    `summary: [${feedbackType}] field=${fieldName} correction=${correction}`,
    "pr_number: ",
  ].join("\n");
}

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.setAttribute("readonly", "");
  textArea.style.position = "absolute";
  textArea.style.left = "-9999px";
  document.body.appendChild(textArea);
  textArea.select();
  document.execCommand("copy");
  document.body.removeChild(textArea);
}

export default function FeedbackForm({ selectedBias }) {
  const [feedbackType, setFeedbackType] = useState("missing-citation");
  const [fieldName, setFieldName] = useState("citations");
  const [correction, setCorrection] = useState("");
  const [doi, setDoi] = useState("");
  const [verdict, setVerdict] = useState("CONFIRMED");
  const [confidence, setConfidence] = useState("medium");
  const [copyStatus, setCopyStatus] = useState("");

  const repoSlug = DEFAULT_REPO.trim();
  const biasId = selectedBias?.id || "";
  const normalizedDoi = doi.trim();
  const isDoiValid = DOI_PATTERN.test(normalizedDoi);
  const showDoiError = normalizedDoi !== "" && !isDoiValid;
  const canSubmit = repoSlug !== "" && biasId !== "" && correction.trim() !== "" && isDoiValid;

  const issueUrl = useMemo(() => {
    if (repoSlug === "" || biasId === "") {
      return "";
    }

    const title = `Feedback: ${biasId}`;
    const body = buildIssueBody({
      biasId,
      feedbackType,
      fieldName,
      correction,
      doi,
      verdict,
      confidence,
    });

    const params = new URLSearchParams({
      labels: "needs-verification",
      title,
      body,
    });

    return `https://github.com/${repoSlug}/issues/new?${params.toString()}`;
  }, [repoSlug, biasId, feedbackType, fieldName, correction, doi, verdict, confidence]);

  const issueBody = useMemo(
    () =>
      buildIssueBody({
        biasId,
        feedbackType,
        fieldName,
        correction,
        doi: normalizedDoi,
        verdict,
        confidence,
      }),
    [biasId, feedbackType, fieldName, correction, normalizedDoi, verdict, confidence],
  );

  const handleSubmit = (event) => {
    event.preventDefault();
    if (!canSubmit || issueUrl === "") {
      return;
    }
    window.open(issueUrl, "_blank", "noopener,noreferrer");
  };

  const handleCopyPayload = async () => {
    setCopyStatus("");
    if (biasId === "" || correction.trim() === "" || normalizedDoi === "") {
      setCopyStatus("Fill bias, correction, and DOI first.");
      return;
    }

    if (!isDoiValid) {
      setCopyStatus("DOI format must match 10.xxxx/xxxx.");
      return;
    }

    try {
      await copyText(issueBody);
      setCopyStatus("Copied payload. Paste into a new GitHub issue body.");
    } catch {
      setCopyStatus("Copy failed. Select and copy from the preview box below.");
    }
  };

  return (
    <form className="card grid" onSubmit={handleSubmit}>
      <h3 style={{ marginTop: 0 }}>Feedback Submission</h3>
      {repoSlug === "" && (
        <p className="small">
          Set VITE_GITHUB_REPO (example: owner/repo) in your local environment to enable issue creation.
        </p>
      )}
      <label>
        Feedback type
        <select value={feedbackType} onChange={(event) => setFeedbackType(event.target.value)}>
          <option value="missing-citation">missing-citation</option>
          <option value="wrong-parameter-link">wrong-parameter-link</option>
          <option value="disputed-mechanism">disputed-mechanism</option>
          <option value="new-fix-attempt">new-fix-attempt</option>
          <option value="new-bias-entry">new-bias-entry</option>
        </select>
      </label>
      <label>
        Bias entry
        <input value={selectedBias?.id || ""} readOnly />
      </label>
      <label>
        Verification verdict
        <select value={verdict} onChange={(event) => setVerdict(event.target.value)}>
          <option value="CONFIRMED">CONFIRMED</option>
          <option value="DISPUTED">DISPUTED</option>
          <option value="REJECTED">REJECTED</option>
        </select>
      </label>
      <label>
        Confidence
        <select value={confidence} onChange={(event) => setConfidence(event.target.value)}>
          <option value="high">high</option>
          <option value="medium">medium</option>
          <option value="low">low</option>
        </select>
      </label>
      <label>
        Specific field
        <input value={fieldName} onChange={(event) => setFieldName(event.target.value)} placeholder="citations" />
      </label>
      <label>
        Your correction
        <textarea value={correction} onChange={(event) => setCorrection(event.target.value)} rows="3" />
      </label>
      <label>
        Supporting DOI
        <input
          value={doi}
          onChange={(event) => setDoi(event.target.value)}
          placeholder="10.xxxx/xxxx"
          aria-invalid={showDoiError}
        />
      </label>
      {showDoiError && <p className="small" style={{ color: "var(--bad)" }}>DOI must match 10.xxxx/xxxx format.</p>}

      <div className="feedback-actions">
        <button type="submit" disabled={!canSubmit}>
          Create Structured Feedback Issue
        </button>
        <button type="button" onClick={handleCopyPayload}>
          Copy Payload
        </button>
      </div>

      {copyStatus !== "" && <p className="small">{copyStatus}</p>}

      <label>
        Payload preview
        <textarea value={issueBody} readOnly rows="6" />
      </label>
    </form>
  );
}
