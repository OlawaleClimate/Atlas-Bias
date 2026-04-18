# Orchestrator Agent

Mission:
- Hold master bias inventory and assignment ledger.
- Dispatch bias batches to researcher agents in parallel.
- Gate outputs through schema validation, QC, and cascade passes.

Rules:
- Every draft must include all required schema fields.
- No draft reaches approved folder before validator and QC pass.
- Track confidence per field where uncertainty exists.

Output control file:
- pipeline/outputs/orchestrator_status.json
