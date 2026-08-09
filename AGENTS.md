# Agent Guide for MCDA

Use the CLI as the state-aware source of truth:

```bash
mcda -C <project-dir> guide
mcda -C <project-dir> next
```

This package is agent-first and JSON-enveloped. Every successful command emits
`{schema_version, command, status, argv, data, warnings, errors, next_steps}`.
Read `next_steps`, execute the appropriate step, and call `mcda next` again.

## EDSL execution boundary

MCDA generates durable EDSL Jobs packages and ingests EDSL Results packages;
it does not execute model calls:

```bash
mcda -C <project-dir> assessment build --id <assessment-id>
ep run <jobs.ep> --output <results.ep>
mcda -C <project-dir> assessment ingest <assessment-id> --results <results.ep>
mcda -C <project-dir> analyze run --method weighted-sum
```

Inspect the returned job counts and paths before running inference. Let EDSL
manage credentials, and never print or commit API keys. Preserve the assessment
manifest and source Results packages as audit evidence.

Use `assessment build --criteria <id,id,...>` when factual performance has already been
recorded for other criteria. Ingestion is complete-by-default and validates the full
expected grid before writing. Inspect its observed/expected coverage before advancing.
Do not use `--allow-partial` unless the user explicitly intends to preserve an incomplete
result set.

## Development checks

```bash
pytest -q
git diff --check
```
