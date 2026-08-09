from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

import typer

from mcda.commands.common import ctx_project, output
from mcda.core.errors import UserError
from mcda.core.ids import local_iso_now, validate_id
from mcda.core.store import append_record, list_entities, read_json, write_json

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _edsl():
    try:
        with redirect_stdout(StringIO()):
            from edsl import Agent, AgentList, Jobs, QuestionNumerical, Results, Scenario, ScenarioList, Survey
        return Agent, AgentList, Jobs, QuestionNumerical, Results, Scenario, ScenarioList, Survey
    except ImportError as exc:
        raise UserError("EDSL is required for assessment build and ingest.", {"install": "pip install edsl"}) from exc


@app.command("build")
def build(
    ctx: typer.Context,
    assessment_id: str = typer.Option(..., "--id"),
    path: Path | None = typer.Option(None, "--path", help="Output .ep path; defaults inside .mcda."),
    criteria: str | None = typer.Option(None, "--criteria", help="Comma-separated leaf criterion IDs."),
) -> None:
    validate_id(assessment_id, "assessment id")
    project = ctx_project(ctx)
    alternatives = list_entities(project, "alternatives")
    all_criteria = [item for item in list_entities(project, "criteria") if item.get("direction")]
    criteria_by_id = {item["id"]: item for item in all_criteria}
    if criteria is None:
        selected_criteria = all_criteria
    else:
        requested = [item.strip() for item in criteria.split(",") if item.strip()]
        duplicates = sorted({item for item in requested if requested.count(item) > 1})
        unknown = sorted(set(requested) - criteria_by_id.keys())
        if not requested or duplicates or unknown:
            raise UserError("--criteria must contain unique leaf criterion IDs.", {
                "requested": requested, "duplicates": duplicates, "unknown": unknown,
                "available": sorted(criteria_by_id),
            })
        selected_criteria = [criteria_by_id[item] for item in requested]
    participants = list_entities(project, "participants")
    if not alternatives or not selected_criteria or not participants:
        raise UserError("Assessment build requires alternatives, leaf criteria, and participants.", {
            "alternatives": len(alternatives), "criteria": len(selected_criteria), "participants": len(participants)
        })
    Agent, AgentList, Jobs, QuestionNumerical, _, Scenario, ScenarioList, Survey = _edsl()
    questions = [QuestionNumerical(
        question_name=item["id"],
        question_text=(f"Estimate {item['name']} for this alternative in {item['unit']}. "
                       f"Return one numeric value.\n\nAlternative: {{{{ alternative_name }}}}\n"
                       f"Description: {{{{ alternative_description }}}}"),
    ) for item in selected_criteria]
    agents = AgentList([Agent(
        traits={"participant_id": item["id"], "participant_name": item["name"], **item.get("traits", {})},
        instruction=item.get("bio") or "Evaluate the alternatives from this participant's perspective.",
    ) for item in participants])
    scenarios = ScenarioList([Scenario({
        "alternative_id": item["id"], "alternative_name": item["name"],
        "alternative_description": item.get("description", ""), "alternative_type": item.get("type", "candidate"),
    }) for item in alternatives])
    jobs = Jobs(survey=Survey(questions, name=f"mcda_{assessment_id}"), agents=agents, scenarios=scenarios)
    assessment_dir = project.path("assessments", assessment_id)
    assessment_dir.mkdir(parents=True, exist_ok=True)
    jobs_path = (path or assessment_dir / "jobs.ep").resolve()
    jobs_path.parent.mkdir(parents=True, exist_ok=True)
    with redirect_stdout(StringIO()):
        saved = jobs.git.save(str(jobs_path), message=f"Create MCDA assessment {assessment_id}")
    actual_path = Path(saved.get("path", jobs_path))
    manifest = {
        "schema_version": 1, "id": assessment_id, "created_at": local_iso_now(),
        "jobs_path": str(actual_path), "results_paths": [],
        "participants": [item["id"] for item in participants],
        "alternatives": [item["id"] for item in alternatives],
        "criteria": [item["id"] for item in selected_criteria],
        "excluded_criteria": [item["id"] for item in all_criteria if item not in selected_criteria],
        "expected_interviews": len(participants) * len(alternatives),
        "expected_answers": len(participants) * len(alternatives) * len(selected_criteria),
    }
    write_json(assessment_dir / "manifest.json", manifest)
    result_path = assessment_dir / "results.ep"
    run_command = f"ep run {actual_path} --output {result_path}"
    output(ctx, {**manifest, "manifest_path": str(assessment_dir / "manifest.json"), "run_command": run_command},
           next_steps=[run_command, f"mcda --project {project.root} assessment ingest {assessment_id} --results {result_path}"])


def _field(row: dict[str, Any], dotted: str) -> Any:
    if dotted in row:
        return row[dotted]
    current: Any = row
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _adapt_rows(rows: list[dict[str, Any]], manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    expected_participants = set(manifest["participants"])
    expected_alternatives = set(manifest["alternatives"])
    criteria = manifest["criteria"]
    observed_interviews: set[tuple[str, str]] = set()
    observed_cells: set[tuple[str, str, str]] = set()
    records: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        participant = _field(row, "agent.participant_id") or _field(row, "participant_id")
        alternative = _field(row, "scenario.alternative_id") or _field(row, "alternative_id")
        if participant not in expected_participants or alternative not in expected_alternatives:
            problems.append({
                "row": index, "participant": participant, "alternative": alternative,
                "problem": "unknown_or_missing_provenance",
            })
            continue
        observed_interviews.add((participant, alternative))
        for criterion in criteria:
            value = _field(row, f"answer.{criterion}")
            if value is None:
                value = _field(row, criterion)
            cell = (participant, alternative, criterion)
            if value is None:
                continue
            if cell in observed_cells:
                problems.append({"row": index, "cell": list(cell), "problem": "duplicate_cell"})
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                problems.append({"row": index, "cell": list(cell), "problem": "not_numeric", "value": value})
                continue
            observed_cells.add(cell)
            records.append({"participant": participant, "alternative": alternative, "criterion": criterion, "value": numeric})
    expected_interviews = {(p, a) for p in expected_participants for a in expected_alternatives}
    expected_cells = {(p, a, c) for p in expected_participants for a in expected_alternatives for c in criteria}
    missing_interviews = sorted(expected_interviews - observed_interviews)
    missing_cells = sorted(expected_cells - observed_cells)
    coverage = {
        "observed_interviews": len(observed_interviews), "expected_interviews": len(expected_interviews),
        "observed_answers": len(observed_cells), "expected_answers": len(expected_cells),
        "missing_interviews": [list(item) for item in missing_interviews],
        "missing_cells": [list(item) for item in missing_cells], "problems": problems,
        "complete": not missing_interviews and not missing_cells and not problems,
    }
    return records, coverage


@app.command("ingest")
def ingest(
    ctx: typer.Context,
    assessment_id: str,
    results: list[Path] = typer.Option(..., "--results"),
    confidence: float = typer.Option(0.5, "--confidence"),
    allow_partial: bool = typer.Option(False, "--allow-partial"),
) -> None:
    project = ctx_project(ctx)
    manifest_path = project.path("assessments", assessment_id, "manifest.json")
    manifest = read_json(manifest_path)
    _, _, _, _, Results, _, _, _ = _edsl()
    pending_records: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    loaded_paths = []
    already_ingested = set(manifest.get("results_paths", []))
    for result_path in results:
        if result_path.suffix != ".ep":
            raise UserError("Assessment results must be an EDSL .ep package.", {"path": str(result_path)})
        resolved_result_path = str(result_path.resolve())
        if resolved_result_path in already_ingested:
            raise UserError("Results package has already been ingested for this assessment.", {
                "assessment": assessment_id, "path": resolved_result_path,
            })
        try:
            with redirect_stdout(StringIO()):
                rows = Results.git.load(str(result_path)).to_dicts()
        except Exception as exc:
            raise UserError("Could not load EDSL Results package.", {"path": str(result_path), "error": str(exc)}) from exc
        all_rows.extend(rows)
        loaded_paths.append(resolved_result_path)
    adapted, coverage = _adapt_rows(all_rows, manifest)
    if not coverage["complete"] and not allow_partial:
        raise UserError("Assessment Results are incomplete or invalid; nothing was imported.", coverage)
    ingested_at = local_iso_now()
    source_paths = loaded_paths
    for record in adapted:
        pending_records.append({
            **record, "confidence": confidence, "recorded_at": ingested_at, "source": "edsl",
            "assessment": assessment_id, "results_paths": source_paths,
        })
    for record in pending_records:
        append_record(project, "perf", [record["participant"], record["alternative"], record["criterion"]], record)
    manifest["results_paths"] = list(dict.fromkeys([*manifest.get("results_paths", []), *loaded_paths]))
    manifest["last_ingested_at"] = local_iso_now()
    manifest["imported_answers"] = manifest.get("imported_answers", 0) + len(pending_records)
    manifest["coverage"] = coverage
    manifest["status"] = "complete" if coverage["complete"] else "partial"
    write_json(manifest_path, manifest)
    warnings = [] if coverage["complete"] else [{"code": "partial_import", "details": coverage}]
    output(ctx, {"assessment": assessment_id, "results_paths": loaded_paths,
                 "imported_answers": len(pending_records), "coverage": coverage}, warnings=warnings,
           next_steps=[f"mcda --project {project.root} analyze run --method weighted-sum"])


@app.command("show")
def show(ctx: typer.Context, assessment_id: str) -> None:
    project = ctx_project(ctx)
    output(ctx, read_json(project.path("assessments", assessment_id, "manifest.json")))
