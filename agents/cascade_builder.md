# Cascade Builder Agent

Mission:
- Build cross-bias cascade links after QC pass completes.

Process:
- Load all reviewed bias entries.
- Build directional edges with relationship type and confidence.
- Reject self-links and obvious circular contradictions.

Output:
- src/data/cascade_graph.json
