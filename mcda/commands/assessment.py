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
) -> None:
    validate_id(assessment_id, "assessment id")
    project = ctx_project(ctx)
    alternatives = list_entities(project, "alternatives")
    criteria = [item for item in list_entities(project, "criteria") if item.get("direction")]
    participants = list_entities(project, "participants")
    if not alternatives or not criteria or not participants:
        raise UserError("Assessment build requires alternatives, leaf criteria, and participants.", {
            "alternatives": len(alternatives), "criteria": len(criteria), "participants": len(participants)
        })
    Agent, AgentList, Jobs, QuestionNumerical, _, Scenario, ScenarioList, Survey = _edsl()
    questions = [QuestionNumerical(
        question_name=item["id"],
        question_text=(f"Estimate {item['name']} for this alternative in {item['unit']}. "
                       f"Return one numeric value.\n\nAlternative: {{{{ alternative_name }}}}\n"
                       f"Description: {{{{ alternative_description }}}}"),
    ) for item in criteria]
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
        "criteria": [item["id"] for item in criteria],
        "expected_interviews": len(participants) * len(alternatives),
        "expected_answers": len(participants) * len(alternatives) * len(criteria),
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


@app.command("ingest")
def ingest(
    ctx: typer.Context,
    assessment_id: str,
    results: list[Path] = typer.Option(..., "--results"),
    confidence: float = typer.Option(0.5, "--confidence"),
) -> None:
    project = ctx_project(ctx)
    manifest_path = project.path("assessments", assessment_id, "manifest.json")
    manifest = read_json(manifest_path)
    _, _, _, _, Results, _, _, _ = _edsl()
    imported = 0
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
        for row in rows:
            participant = _field(row, "agent.participant_id") or _field(row, "participant_id")
            alternative = _field(row, "scenario.alternative_id") or _field(row, "alternative_id")
            if not participant or not alternative:
                raise UserError("Results row is missing participant or alternative provenance.", {"keys": sorted(row)})
            for criterion in manifest["criteria"]:
                value = _field(row, f"answer.{criterion}")
                if value is None:
                    continue
                try:
                    numeric = float(value)
                except (TypeError, ValueError) as exc:
                    raise UserError("A criterion answer is not numeric.", {"criterion": criterion, "value": value}) from exc
                record = {
                    "participant": participant, "alternative": alternative, "criterion": criterion,
                    "value": numeric, "confidence": confidence, "recorded_at": local_iso_now(),
                    "source": "edsl", "assessment": assessment_id, "results_path": resolved_result_path,
                }
                append_record(project, "perf", [participant, alternative, criterion], record)
                imported += 1
        loaded_paths.append(resolved_result_path)
    manifest["results_paths"] = list(dict.fromkeys([*manifest.get("results_paths", []), *loaded_paths]))
    manifest["last_ingested_at"] = local_iso_now()
    manifest["imported_answers"] = manifest.get("imported_answers", 0) + imported
    write_json(manifest_path, manifest)
    output(ctx, {"assessment": assessment_id, "results_paths": loaded_paths, "imported_answers": imported},
           next_steps=[f"mcda --project {project.root} analyze run --method weighted-sum"])


@app.command("show")
def show(ctx: typer.Context, assessment_id: str) -> None:
    project = ctx_project(ctx)
    output(ctx, read_json(project.path("assessments", assessment_id, "manifest.json")))
