from __future__ import annotations

import typer

from mcda.commands.common import ctx_project, maybe_session, output
from mcda.core.criteria import leaf_criteria, validate_tree
from mcda.core.store import list_entities, list_records, read_json


def command(ctx: typer.Context) -> None:
    project = ctx_project(ctx)
    meta = read_json(project.path("meta.json"))
    alternatives = list_entities(project, "alternatives")
    criteria = list_entities(project, "criteria")
    participants = list_entities(project, "participants")
    leaves = leaf_criteria(criteria)
    issues = validate_tree(criteria)
    if not any(alt.get("type") == "candidate" for alt in alternatives):
        issues.append("Add at least one candidate alternative.")
    if not leaves:
        issues.append("Add at least one leaf criterion.")
    if not participants:
        issues.append("Add at least one participant.")
    data = {
        "project": str(project.root),
        "data_dir": str(project.data_dir),
        "meta": meta,
        "counts": {
            "alternatives": len(alternatives),
            "candidate_alternatives": len([alt for alt in alternatives if alt.get("type") == "candidate"]),
            "reference_alternatives": len([alt for alt in alternatives if alt.get("type") == "reference"]),
            "criteria": len(criteria),
            "leaf_criteria": len(leaves),
            "participants": len(participants),
            "weights": len(list_records(project, "weights")),
            "thresholds": len(list_records(project, "thresholds")),
            "perf": len(list_records(project, "perf")),
            "results": len(list_records(project, "results")),
        },
        "current_session": maybe_session(project),
        "checklist": issues,
    }
    output(ctx, data)
