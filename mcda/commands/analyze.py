from __future__ import annotations

import typer

from mcda.commands.common import ctx_project, output
from mcda.core.aggregate import aggregate_thresholds, aggregate_values
from mcda.core.criteria import compute_global_weights, leaf_criteria, validate_tree
from mcda.core.electre3 import analyze as electre3_analyze
from mcda.core.errors import AnalysisError
from mcda.core.ids import local_iso_now, record_id
from mcda.core.store import latest_by, list_entities, list_records, read_json, write_json

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("run")
def run(
    ctx: typer.Context,
    weights_from: str = typer.Option("median", "--weights-from"),
    perf_from: str = typer.Option("confidence-weighted-mean", "--perf-from"),
    thresholds_from: str = typer.Option("median", "--thresholds-from"),
    participant: str | None = typer.Option(None, "--participant"),
    lambda_cut: float | None = typer.Option(None, "--lambda"),
) -> None:
    project = ctx_project(ctx)
    if participant:
        weights_from = perf_from = thresholds_from = f"facilitator:{participant}"
    meta = read_json(project.path("meta.json"))
    lambda_value = float(lambda_cut if lambda_cut is not None else meta.get("settings", {}).get("lambda", 0.75))
    alternatives = list_entities(project, "alternatives")
    criteria = list_entities(project, "criteria")
    participants = {p["id"]: p for p in list_entities(project, "participants")}
    warnings: list[dict] = []
    issues = validate_tree(criteria)
    leaves = leaf_criteria(criteria)
    if not alternatives:
        issues.append("At least one alternative is required.")
    if not any(alt.get("type") == "candidate" for alt in alternatives):
        issues.append("At least one candidate alternative is required.")
    if not leaves:
        issues.append("At least one leaf criterion is required.")
    if not 0.5 < lambda_value <= 1.0:
        issues.append("lambda must be in (0.5, 1.0].")
    if issues:
        raise AnalysisError("Validation failed.", {"issues": issues})

    participant_ids = list(participants)
    latest_weights = latest_by(list_records(project, "weights"), ("participant", "criterion"))
    latest_thresholds = latest_by(list_records(project, "thresholds"), ("participant", "criterion"))
    latest_perf = latest_by(list_records(project, "perf"), ("participant", "alternative", "criterion"))

    local_weights = {}
    for criterion in criteria:
        entries = {
            pid: (latest_weights.get((pid, criterion["id"])) or (None, None))[1]
            for pid in participant_ids
        }
        local_weights[criterion["id"]] = aggregate_values(entries, weights_from, participants)
    global_weights = compute_global_weights(criteria, local_weights)

    resolved_thresholds = {}
    for criterion in leaves:
        entries = {
            pid: (latest_thresholds.get((pid, criterion["id"])) or (None, None))[1]
            for pid in participant_ids
        }
        resolved, threshold_warnings = aggregate_thresholds(entries, thresholds_from, participants)
        warnings.extend(threshold_warnings)
        q, p, v = resolved["q"], resolved["p"], resolved["v"]
        if q is None or p is None or q < 0 or p < q or (v is not None and v < p):
            raise AnalysisError("Invalid resolved threshold.", {"criterion": criterion["id"], "threshold": resolved})
        resolved_thresholds[criterion["id"]] = resolved

    resolved_perf = {}
    for alternative in alternatives:
        alt_perf = {}
        for criterion in leaves:
            entries = {
                pid: (latest_perf.get((pid, alternative["id"], criterion["id"])) or (None, None))[1]
                for pid in participant_ids
            }
            alt_perf[criterion["id"]] = aggregate_values(entries, perf_from, participants, abstention_policy="exclude-participant")
        resolved_perf[alternative["id"]] = alt_perf

    electre = electre3_analyze(alternatives, leaves, global_weights, resolved_thresholds, resolved_perf, lambda_value)
    rid = record_id("electre-iii")
    result = {
        "id": rid,
        "method": "electre-iii",
        "run_at": local_iso_now(),
        "aggregation": {"weights": weights_from, "perf": perf_from, "thresholds": thresholds_from},
        "resolved_weights": global_weights,
        "resolved_thresholds": resolved_thresholds,
        "resolved_perf": resolved_perf,
        **electre,
    }
    write_json(project.path("results", f"{rid}.json"), result)
    output(ctx, result, warnings=warnings)


@app.command("ranking")
def ranking(ctx: typer.Context, include_references: bool = typer.Option(False, "--include-references")) -> None:
    project = ctx_project(ctx)
    records = list_records(project, "results")
    if not records:
        raise AnalysisError("No results found.")
    _, result = records[-1]
    data = result["distillation"]["final"] if include_references else result["candidate_ranking"]
    output(ctx, data)
