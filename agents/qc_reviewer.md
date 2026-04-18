# QC Reviewer Agent

Mission:
- Verify citation integrity and causal consistency.

Execution:
- Run python agents/run_qc_review.py.
- Optional strict mode: python agents/run_qc_review.py --fail-on-warning.

Checks:
- DOI present and plausibly formatted.
- Severity/parameterization claims align with cited context.
- Fix attempt outcomes do not contradict side-effect notes.
- Cascade targets reference known bias IDs.

Output:
- Pass: pipeline/outputs/reviewed/<bias-id>.json
- Flag: pipeline/outputs/reviewed/<bias-id>.flag.json

Exit behavior:
- Non-zero on any errors.
- Non-zero on warnings only when strict mode is enabled.
