# Climate Model Bias Atlas — Full Build Plan

A structured, interactive, living reference tool cataloging systematic biases in climate
models — causes, parameterization links, fix histories, cascade chains, and
community-verified updates. Companion tool to the Config Comparison App, sharing the
same parameter namespace.

---

## What It Is

The atlas answers two questions no existing tool answers:

> *"Which models have this bias, what parameterization causes it, and what has been
> tried to fix it?"*

> *"I changed this parameter — what biases is that known to affect?"*

Every existing tool (ES-DOC, GCMeval, ESMValTool) treats biases as outputs to measure.
None link biases back to parameterizations that cause them, fix attempts that were made,
or cascade chains connecting one bias to another. That causal chain currently lives
scattered across hundreds of papers in GMD, JAMES, and J. Climate. The atlas makes it
navigable for the first time.

---

## Technology Stack

| Layer | Choice | Reason |
|---|---|---|
| Frontend | React + Vite | Same stack as Config Comparison App |
| Styling | Plain CSS + variables | Dark scientific instrument aesthetic |
| Equations | KaTeX | Render parameterization equations inline |
| Graph viz | D3 or React Flow | Cascade relationship visualization |
| Data | JSON files in repo | Versioned, citable, agent-writable |
| Feedback | GitHub Issues + Actions | Public, auditable, automated |
| CI/CD | GitHub Actions + Vercel | Auto-rebuild on data merge |
| Archiving | Zenodo auto-release | Citable DOI per version |

---

## The Full Pipeline

```
Phase 0: Schema Design
        ↓
Phase 1: Data Pipeline (multi-agent)
        ↓
HUMAN PAUSE 1: Domain Review
        ↓
Phase 2: Build Pipeline (build agents)
        ↓
HUMAN PAUSE 2: UI Review
        ↓
Deploy
        ↓
Phase 3: Feedback Loop (ongoing, automated)
```

Two human pauses. Everything else is automated.

---

## Phase 0 — Schema Design

**Do this before anything else. The schema is the contract everything depends on.**

One focused session designing every field, type, and relationship in the bias record.
Every agent prompt, every validation rule, every component, every GitHub Action is
determined by this schema.

### Bias Record Schema (fields to define)

```js
{
  // Core identity
  id:                  string          // "double-itcz"
  name:                string          // "Double ITCZ"
  version:             string          // "1.3"
  last_updated:        ISO date
  category:            enum            // precipitation | temperature | circulation
                                       // clouds | ocean | land | sea_ice
  region:              string          // "tropical_pacific"
  season:              string          // "annual" | "DJF" | "JJA" etc.
  affected_variables:  string[]        // ["pr", "omega", "SST"]
  description:         string          // physical description
  persistence:         enum            // longstanding | improved | resolved | introduced

  // CMIP generation history
  cmip_history: [
    {
      generation:  enum    // CMIP3 | CMIP5 | CMIP6 | CMIP7
      severity:    enum    // strong | moderate | weak | absent
      notes:       string
    }
  ]

  // Model severity
  severity_by_model: {
    [model_id]: {
      severity:    enum    // strong | moderate | weak | absent
      direction:   string  // "wet" | "warm" | "cold" | "dry" etc.
      source:      string  // citation for this rating
    }
  }

  // Parameterization links
  implicated_params: [
    {
      subsystem:   string  // "convection"
      parameter:   string  // "cape_threshold_J_kg"
      role:        string  // physical explanation
      type:        enum    // primary | secondary
      evidence:    string  // citation
    }
  ]

  // Fix attempts
  fix_attempts: [
    {
      model:       string
      version:     string
      change:      string  // what was changed
      mechanism:   string  // why it was expected to help
      outcome:     enum    // success | partial | backfired | unknown
      side_effects: string // unintended consequences
      reference:   string  // citation
    }
  ]

  // Cascade relationships
  cascade_links: [
    {
      target_bias:       string  // bias id
      relationship:      enum    // causes | amplifies | masks
                                 // triggered_by | resolved_by
      evidence:          string
      confidence:        enum    // high | medium | low
    }
  ]

  // Disputed mechanisms
  disputed_mechanisms: [
    {
      claim:        string
      view_a:       { description, citations[] }
      view_b:       { description, citations[] }
      status:       string  // "unresolved as of CMIP6"
    }
  ]

  // Citations
  citations: [
    {
      authors:     string
      year:        number
      journal:     string
      doi:         string
      relevance:   string
    }
  ]

  // Feedback and versioning
  feedback_history: [
    {
      issue_number:   number
      type:           string
      submitted_by:   string
      date:           ISO date
      verdict:        enum    // CONFIRMED | DISPUTED | REJECTED
      confidence:     enum    // high | medium | low
      pr_number:      number  // if PR was created
    }
  ]

  changelog: [
    {
      version:        string
      date:           ISO date
      change:         string
      submitted_by:   string
      issue:          number
      pr:             number
      verified_by:    string
      approved_by:    string
    }
  ]
}
```

---

## Phase 1 — Data Pipeline

**Goal:** 47 validated, citation-backed bias records in JSON

### Bias Inventory (~47 entries)

| Category | Biases | Count |
|---|---|---|
| Precipitation / ITCZ | Double ITCZ, Tropical timing (diurnal), Sahel dry, Amazon dry season, Monsoon onset, ITCZ width | 6 |
| Temperature / SST | Southern Ocean warm SST, Arctic amplification, Tropical cold troposphere, Cold tongue, Land warm bias (semi-arid), NW Pacific cold SST, NE Pacific warm SST, Global mean SST shift | 8 |
| Circulation | AMOC strength, Jet stream equatorward, MJO propagation speed, Blocking frequency, ENSO amplitude, Hadley cell expansion, NAO representation | 7 |
| Clouds / Radiation | Southern Ocean shortwave, Low cloud underestimate (stratocumulus), High ECS / hot model problem, TOA energy drift, Tropical cloud anvil, Cloud phase | 6 |
| Ocean | Mixed layer depth, Deep ocean ventilation, Subtropical gyre bias, ACC transport, Equatorial upwelling | 5 |
| Land surface | Central US warm/dry, Permafrost extent, Soil moisture coupling, Albedo in semi-arid | 4 |
| Sea ice | Arctic extent loss rate, Antarctic sea ice trend, Sea ice thickness | 3 |
| Resolved / historical | CMIP3 tropical cold bias, Early runaway sea ice, Old convective adjustment, Pre-CMIP5 ocean drift, CMIP5 Southern Ocean fix story, Flux correction era, AMIP SST cold bias, Early land carbon | 8 |
| **Total** | | **47** |

### Agent Team

```
Orchestrator Agent
├── Holds master bias list
├── Assigns one bias per research agent
├── Tracks completion status
└── Routes outputs through pipeline

Research Agents ×10 (parallel)
├── Each owns 4-5 bias entries end to end
├── Deep literature search per entry
├── Outputs structured draft matching schema exactly
└── Tags confidence per field: high | medium | low

Schema Validator Agent
├── Validates every output against agreed schema
├── Catches missing fields, wrong types, malformed DOIs
└── Returns to research agent for correction

QC Agent
├── Cross-checks citations (DOIs real, claims match abstracts)
├── Checks logical consistency (cause connects to parameterization)
└── Flags items needing domain review vs safe to pass

Cascade Agent (runs after all records pass QC)
├── Reads full set of approved records
├── Identifies cascade links across entries
├── Checks for circular reasoning and directional inconsistencies
└── Outputs cascade_graph.json as separate structure
```

### Pipeline Folder Structure

```
pipeline/
├── agents/
│   ├── orchestrator.md
│   ├── researcher.md
│   ├── schema_validator.md
│   ├── qc_reviewer.md
│   └── cascade_builder.md
├── schema/
│   └── bias_record_schema.json
└── outputs/
    ├── drafts/          # Raw agent outputs
    ├── validated/       # Post schema check
    ├── reviewed/        # Post QC
    └── approved/        # Post domain review
```

### HUMAN PAUSE 1 — Domain Review

You review flagged items (expected ~8-12 of 47), spot-check 5 random passed entries,
verify cascade graph makes scientific sense, approve or send back for re-research.

**Your active time: 2–3 hours**

---

## Phase 2 — Build Pipeline

**Goal:** Full React app built directly against approved data

### Agent Team

```
Data Layer Agent
├── Converts approved JSON to src/data/biases.js
├── Builds search indexes (by category, model, parameter)
├── Optimizes for UI query patterns
└── Outputs src/data/cascade_graph.json for graph viz

Component Agent
├── BiasCard.jsx          ← one bias record
├── ModelSeverityBar.jsx  ← severity per model
├── CascadeGraph.jsx      ← D3/React Flow relationship viz
├── FixTimeline.jsx       ← fix attempts over time
├── GenerationBadge.jsx   ← CMIP3/5/6 severity indicator
├── FeedbackForm.jsx      ← structured feedback submission
└── ReviewQueue.jsx       ← your admin review interface

Layout Agent
├── BrowseByBias.jsx      ← sidebar + bias detail view
├── BrowseByModel.jsx     ← model profile view
├── BrowseByParam.jsx     ← parameter → bias lookup
└── App.jsx               ← top-level routing

Style Agent
├── Applies dark scientific instrument aesthetic
├── Monospace for parameter values
├── Semantic colors: amber=changed, green=resolved,
│   red=introduced/backfired, gray=same
└── KaTeX equation styling

Integration Agent
├── Reads Config Comparison App codebase
├── Reads Bias Atlas codebase
├── Builds shared parameter namespace bridge
└── Adds bias implication badges to config diff rows

Test Agent
├── Smoke tests: every bias record renders without errors
├── Reference tests: all cascade links resolve to real entries
├── Filter tests: category/model/parameter filters return
│   expected results
└── Integration tests: config app parameter links resolve
```

### App Structure

```
src/
├── data/
│   ├── biases.js              # 47 bias records
│   ├── cascade_graph.json     # Relationship graph
│   └── models.js              # Shared with Config Comparison App
├── components/
│   ├── BiasCard.jsx
│   ├── ModelSeverityBar.jsx
│   ├── CascadeGraph.jsx
│   ├── FixTimeline.jsx
│   ├── GenerationBadge.jsx
│   ├── FeedbackForm.jsx
│   └── ReviewQueue.jsx
├── views/
│   ├── BrowseByBias.jsx
│   ├── BrowseByModel.jsx
│   └── BrowseByParam.jsx
└── App.jsx
```

### HUMAN PAUSE 2 — UI Review

You check scientific content renders correctly, cascade visualization is navigable,
config app integration feels right, aesthetic is appropriate.

**Your active time: 1–2 hours**

---

## Phase 3 — Feedback Loop (Ongoing)

**Goal:** Living tool that self-improves from community input, fully automated
except for your final approval

### Full Flow

```
User submits structured feedback form in app
        ↓
GitHub Issue auto-created with structured body + labels
        ↓
GitHub Action triggers Verification Agent
        ↓
Agent deep-researches the specific claim
        ↓
Agent posts finding as Issue comment
        ↓
CONFIRMED  → Agent auto-creates PR with JSON diff + changelog entry
DISPUTED   → Agent posts both sides, Issue stays open for your judgment
REJECTED   → Agent closes Issue with explanation
        ↓
YOU review PR (or comment on disputed Issue)
        ↓
Merge PR → GitHub Action triggers app rebuild → Vercel deploy
        ↓
Zenodo auto-archives new version with DOI (on tagged releases)
```

### Feedback Types

| Type | Agent Action | PR Created |
|---|---|---|
| Missing citation | Verifies paper relevance + adds to citations array | Yes if confirmed |
| Wrong parameter link | Researches both claims + proposes correction | Yes if confirmed |
| Disputed mechanism | Presents both sides with citations | No — your judgment |
| New fix attempt | Extracts structured data + validates schema | Yes if confirmed |
| New bias entry | Full deep research → complete draft record | Yes if confirmed |

### Feedback Form (Structured Input)

```
Feedback type:      [ dropdown ]
Bias entry:         [ auto-filled from current page ]
Specific field:     [ dropdown ]
Your correction:    [ text area ]
Supporting DOI:     [ input, optional ]
Your name/org:      [ input, optional ]
```

Structured input means the agent immediately knows which field to check, which record
to load, and what claim to research. No ambiguity to resolve.

### GitHub Issue Format (Auto-Created)

```markdown
Title: [FEEDBACK] double-itcz — missing-citation
Labels: missing-citation, needs-verification, double-itcz

## Feedback Type
missing-citation

## Bias Entry
double-itcz

## Specific Field
citations

## Submission
Missing Tian & Dong 2020 GRL which quantifies bias across CMIP3/5/6.

## Supporting Reference
doi:10.1029/2020GL087232
```

### Agent Comment on Issue (Auto-Posted)

```markdown
## Verification Agent Finding

**Verdict:** CONFIRMED
**Confidence:** High

**Finding:** Tian & Dong (2020, GRL) directly quantifies the double-ITCZ
bias across CMIP3/5/6 using TPAI and EPI indices. Widely cited (47
citations). Adds cross-generational context not in current record.

**Proposed change:** Add to citations array.

A pull request has been automatically created: #142
@owner — please review and merge if approved.
```

### Auto-Created PR Format

```markdown
Title: [Verified Feedback] Add Tian & Dong 2020 citation (closes #141)

## What Changed
Added citation to double-itcz entry citations array.

## Agent Finding
[finding pasted here]

## JSON Diff
+ {
+   "authors": "Tian & Dong",
+   "year": 2020,
+   "journal": "Geophysical Research Letters",
+   "doi": "10.1029/2020GL087232",
+   "relevance": "Cross-CMIP3/5/6 quantification using TPAI and EPI"
+ }

## Changelog Entry Added
{
  "version": "1.3",
  "date": "2026-04-15",
  "change": "Added Tian & Dong 2020 citation",
  "submitted_by": "J. Smith, NCAR",
  "issue": 141,
  "pr": 142,
  "verified_by": "Verification Agent",
  "confidence": "high",
  "approved_by": "pending"
}
```

### GitHub Actions Required

```yaml
# 1. Trigger verification on new feedback issue
on:
  issues:
    types: [opened]
    labels: [needs-verification]
→ runs: agents/verify_feedback.py

# 2. Rebuild and deploy on data merge
on:
  push:
    branches: [main]
    paths: [src/data/**.json]
→ runs: npm build → Vercel deploy

# 3. Zenodo archive on tagged release
on:
  release:
    types: [published]
→ runs: Zenodo upload → mints DOI
```

---

## Connection to Config Comparison App

Shared parameter namespace between both tools. In the Config Comparison App:

```
cape_threshold_J_kg  |  70  |  100  |  CHANGED  ⚠ 2 known biases
```

Click the badge → Bias Atlas opens filtered to biases where `cape_threshold_J_kg`
is listed in `implicated_params`. Two tools, one coherent workflow:

**Compare configurations → understand what biases those configurations drive**

---

## Scientific Credibility Properties

| Property | How it's achieved |
|---|---|
| Every claim cited | Primary source DOI required per field |
| Disputes shown honestly | `disputed_mechanisms` field, not false consensus |
| Full audit trail | Issue + agent finding + PR + merge, all public on GitHub |
| Versioned and citable | Changelog per entry, Zenodo DOI per release |
| Community trust | All verification findings are public on GitHub Issues |
| Your expertise as gate | Nothing enters data without your approval |

---

## Repository Structure

```
bias-atlas/
├── src/
│   ├── data/
│   │   ├── entries/           # One JSON file per bias
│   │   ├── cascade_graph.json
│   │   └── models.js
│   ├── components/
│   ├── views/
│   └── App.jsx
├── agents/
│   ├── orchestrator.md
│   ├── researcher.md
│   ├── schema_validator.md
│   ├── qc_reviewer.md
│   ├── cascade_builder.md
│   ├── verify_feedback.py     # GitHub Action script
│   └── update_record.py       # Applies approved diffs
├── schema/
│   └── bias_record_schema.json
├── pipeline/
│   └── outputs/
│       ├── drafts/
│       ├── validated/
│       ├── reviewed/
│       └── approved/
├── .github/
│   └── workflows/
│       ├── verify-feedback.yml
│       ├── rebuild-on-merge.yml
│       └── zenodo-release.yml
└── README.md
```

---

## Total Estimated Active Time

| Task | Your time |
|---|---|
| Schema design | 2–3 hours |
| Domain review (Phase 1) | 2–3 hours |
| UI review (Phase 2) | 1–2 hours |
| Ongoing feedback review | Minutes per item |
| **Total to launch** | **~8 hours** |

---

## Execution Order

1. **Design JSON schema** — one session, every field locked down
2. **Write agent instruction files** — one per agent role (6 files)
3. **Run data pipeline** in Claude Code — parallel research, review outputs
4. **Run build pipeline** in Claude Code — review UI
5. **Configure GitHub Actions** — feedback loop, rebuild trigger, Zenodo
6. **Deploy to Vercel** — live app
7. **Tag v1.0 release** — Zenodo mints first citable DOI

---

## What Comes Next After v1

- ML emulator bias profiles (GraphCast, ACE2, GenCast, FuXi-S2S)
- CMIP7 entries as they emerge
- Map-based spatial visualization of bias regions
- Integration with S2D Predictability Explorer (separate tool)
- Community contribution workflow for new bias entries
- GMD or ESSI publication describing the tool and data model
