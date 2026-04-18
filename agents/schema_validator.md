# Schema Validator Agent

Mission:
- Validate each draft against schema/bias_record_schema.json.

Execution:
- Run python agents/run_schema_validation.py.

Checks:
- Missing required keys
- Wrong enum values
- Wrong primitive types
- Malformed date strings

If invalid:
- Write error report to pipeline/outputs/drafts/<bias-id>.errors.json.

If valid:
- Write to pipeline/outputs/validated/<bias-id>.json
