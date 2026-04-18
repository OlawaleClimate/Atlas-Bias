# Climate Model Bias Atlas

Interactive reference for climate model bias causality, parameterization links,
fix histories, and cascade chains.

## Build Status

This repository is being rebuilt to the BIAS_ATLAS_BUILD_PLAN specification.
Current state includes:
- Phase 0 schema contract in schema/bias_record_schema.json
- Phase 1 pipeline folder scaffold and agent instructions
- React + Vite frontend shell with Browse by Bias, Model, and Parameter views
- GitHub Action workflow stubs for feedback verification and rebuild

## Stack

- React + Vite
- Plain CSS with scientific dark theme variables
- KaTeX dependency included for equation rendering
- JSON record store under src/data/entries

## Run

1. npm install
2. Copy .env.example to .env
3. Set VITE_GITHUB_REPO in .env to your repository slug (owner/repo)
4. npm run validate:data:strict
5. npm run dev
6. Open http://localhost:5173

Optional for feedback issue creation from the UI:
- Set VITE_GITHUB_REPO to your repository slug, for example owner/repo.
- macOS/Linux example: export VITE_GITHUB_REPO=owner/repo

## Host on GitHub Pages

If local npm is blocked by enterprise certificate restrictions, use GitHub-hosted builds:

1. Push this repo to GitHub.
2. In GitHub, open Settings -> Pages.
3. Set Source to GitHub Actions.
4. Push to main or run the Deploy GitHub Pages workflow manually.
5. Open the published URL shown by the workflow run.

Notes:
- Workflow file: .github/workflows/deploy-github-pages.yml
- Vite base path is set automatically for project pages and user pages.

## Core Paths

- src/data/entries: one JSON bias record per file
- schema/bias_record_schema.json: validation contract
- agents: agent role instructions and automation stubs
- pipeline/outputs: draft to approved progression
- .github/workflows: automation entry points

## Next Build Steps

1. Complete full 47-entry inventory in src/data/entries
2. Implement schema validator and QC execution scripts
3. Implement GitHub issue to PR feedback automation
4. Add full cascade graph UI with navigation and confidence filtering
