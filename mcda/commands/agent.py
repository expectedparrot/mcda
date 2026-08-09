from __future__ import annotations

import typer

from mcda.commands.common import ctx_project, output
from mcda.core.errors import ProjectNotFound
from mcda.core.store import list_entities, list_records, read_json


def _state(project):
    alternatives = list_entities(project, "alternatives")
    criteria = [item for item in list_entities(project, "criteria") if item.get("direction")]
    participants = list_entities(project, "participants")
    assessments = sorted(project.path("assessments").glob("*/manifest.json"))
    assessment_states = [read_json(path) for path in assessments]
    results = sorted(project.path("results").glob("*.json"))
    performance_keys = {
        (record.get("participant"), record.get("alternative"), record.get("criterion"))
        for _, record in list_records(project, "perf") if not record.get("abstention")
    }
    required_keys = {(p["id"], a["id"], c["id"]) for p in participants for a in alternatives for c in criteria}
    return {
        "project": str(project.root),
        "counts": {
            "alternatives": len(alternatives), "criteria": len(criteria),
            "participants": len(participants), "performance_records": len(list_records(project, "perf")),
            "weight_records": len(list_records(project, "weights")),
            "assessments": len(assessments), "analyses": len(results),
            "required_performance_cells": len(required_keys),
            "covered_performance_cells": len(required_keys & performance_keys),
            "missing_performance_cells": len(required_keys - performance_keys),
        },
        "assessment_manifests": [str(path) for path in assessments],
        "assessments": [{"id": item["id"], "status": item.get("status", "awaiting_results"),
                         "coverage": item.get("coverage")} for item in assessment_states],
    }


def _recommendation(state: dict) -> tuple[str, str]:
    counts = state["counts"]
    if not counts["alternatives"]:
        return "mcda alt add <id> <name>", "Define the decision alternatives."
    if not counts["criteria"]:
        return "mcda crit add <id> <name> --direction <min|max> --unit <unit>", "Define at least one measurable criterion."
    if not counts["participants"]:
        return "mcda participant add <id> <name>", "Add the people or digital-twin perspectives that will evaluate alternatives."
    if not counts["weight_records"]:
        return "mcda weights set <participant-id> <criterion-id> <weight>", "Record criterion importance before analysis."
    if counts["missing_performance_cells"] and not counts["assessments"]:
        return "mcda assessment build --id round_1", "Generate EDSL Jobs for agent-based performance elicitation."
    if counts["missing_performance_cells"] and counts["assessments"]:
        return "ep run <jobs.ep> --output <results.ep>", "Run generated Jobs outside mcda, then ingest the Results package."
    if not counts["analyses"]:
        return "mcda analyze run --method weighted-sum", "Analyze the collected evidence."
    return "mcda analyze ranking", "Inspect the current decision ranking."


def capabilities(ctx: typer.Context) -> None:
    output(ctx, {
        "agent_first": True, "json_envelope_schema": "1.0",
        "edsl_boundary": "mcda generates Jobs and ingests Results; it never executes model calls",
        "commands": ["guide", "next", "assessment build", "assessment ingest", "analyze run"],
    }, next_steps=["mcda guide"])


def guide(ctx: typer.Context) -> None:
    try:
        state = _state(ctx_project(ctx))
        command, reason = _recommendation(state)
    except ProjectNotFound:
        state = {"project": None}
        command, reason = "mcda init <project_name>", "Create a project first."
    output(ctx, {
        "workflow": [
            "Define alternatives, criteria, and participants.",
            "Record weights and thresholds directly or generate an EDSL assessment.",
            "Run generated .ep Jobs externally with ep run.",
            "Ingest the resulting .ep Results package.",
            "Analyze and inspect the ranking.",
        ],
        "execution_boundary": "Model inference is external. mcda does not run EDSL Jobs.",
        "state": state, "recommendation": command, "reason": reason,
    }, next_steps=[command])


def next_command(ctx: typer.Context) -> None:
    try:
        state = _state(ctx_project(ctx))
        command, reason = _recommendation(state)
    except ProjectNotFound:
        state = {"project": None}
        command, reason = "mcda init <project_name>", "No MCDA project was found."
    output(ctx, {"recommendation": command, "reason": reason, "state": state}, next_steps=[command])
