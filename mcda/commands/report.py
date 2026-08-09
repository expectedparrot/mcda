from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import typer

from mcda.commands.common import ctx_project, output
from mcda.core.criteria import leaf_criteria
from mcda.core.store import latest_by, list_entities, list_records, read_json

app = typer.Typer(no_args_is_help=True, add_completion=False)

SECTIONS = [
    "Executive recommendation", "Decision context", "Alternatives and reference option",
    "Criteria and evidence", "Stakeholder weights and provenance", "Method and missing-data policy",
    "Candidate ranking", "Reference-inclusive comparison", "Drivers, tradeoffs, and disagreements",
    "Robustness and uncertainty", "Limitations and next validation", "Appendix: audit trail",
]

WRITING_RULES = [
    "Distinguish factual/direct inputs from EDSL-simulated judgments and preserve their provenance.",
    "Do not present simulated participant judgments as observed population evidence.",
    "Explain ties, incomparability, vetoes, and disagreement between methods when the evidence contains them.",
    "Do not invent sensitivity, robustness, or participant-specific findings that MCDA has not computed.",
    "Treat reference alternatives as comparators, not recommendation candidates.",
    "Cite canonical artifact paths or stable record IDs for material claims.",
]


def _relative(project, path: Path) -> str:
    try:
        return str(path.relative_to(project.root))
    except ValueError:
        return str(path)


def build_guide(project) -> dict[str, Any]:
    meta_path = project.path("meta.json")
    meta = read_json(meta_path)
    alternatives = list_entities(project, "alternatives")
    criteria = list_entities(project, "criteria")
    leaves = leaf_criteria(criteria)
    participants = list_entities(project, "participants")
    weights = list_records(project, "weights")
    thresholds = list_records(project, "thresholds")
    performance = list_records(project, "perf")
    analyses = list_records(project, "results")
    primary_selections = list_records(project, "analysis_selections")
    assessment_paths = sorted(project.path("assessments").glob("*/manifest.json"))
    assessments = [(path, read_json(path)) for path in assessment_paths]

    latest_perf = latest_by(performance, ("participant", "alternative", "criterion"))
    expected_cells = {
        (participant["id"], alternative["id"], criterion["id"])
        for participant in participants for alternative in alternatives for criterion in leaves
    }
    observed_cells = {
        key for key, (_, record) in latest_perf.items()
        if key in expected_cells and not record.get("abstention") and record.get("value") is not None
    }
    missing_cells = sorted(expected_cells - observed_cells)
    source_counts = Counter(record.get("source", "unknown") for _, record in performance)
    assessment_counts = Counter(record.get("assessment") for _, record in performance if record.get("assessment"))

    analysis_summaries = []
    for result_id, result in analyses:
        path = project.path("results", f"{result_id}.json")
        aggregation = result.get("aggregation", {})
        participant_specific = any(str(value).startswith("facilitator:") for value in aggregation.values())
        analysis_summaries.append({
            "id": result.get("id", result_id), "path": _relative(project, path),
            "method": result.get("method"), "run_at": result.get("run_at"),
            "role": result.get("role") or ("robustness" if participant_specific else None),
            "participant": result.get("participant"), "participant_specific": participant_specific,
            "aggregation": aggregation,
            "candidate_ranking": result.get("candidate_ranking"),
            "reference_ranking": result.get("reference_ranking"),
            "reference_inclusive_ranking": result.get("ranking") or result.get("distillation", {}).get("final"),
            "available_diagnostics": sorted(key for key in (
                "weighted_contributions", "scores", "normalized_perf", "credibility", "concordance",
                "relations", "distillation", "resolved_weights", "resolved_thresholds", "resolved_perf",
            ) if key in result),
            "warnings": result.get("warnings", []),
        })
    analyses_by_id = {item["id"]: item for item in analysis_summaries}
    selected_id = primary_selections[-1][1].get("analysis_id") if primary_selections else None
    primary = analyses_by_id.get(selected_id) if selected_id else None
    primary_selection_problem = None
    inferred_primary = False
    if selected_id and primary is None:
        primary_selection_problem = "missing_selected_analysis"
    elif not selected_id and analysis_summaries:
        eligible = [item for item in analysis_summaries if not item["participant_specific"]]
        if len(eligible) == 1:
            primary = eligible[0]
            inferred_primary = True
        elif len(eligible) > 1:
            primary_selection_problem = "ambiguous_primary"
        else:
            primary_selection_problem = "no_eligible_primary"

    assessment_summaries = [{
        "id": manifest.get("id"), "manifest_path": _relative(project, path),
        "status": manifest.get("status", "awaiting_results"),
        "jobs_path": manifest.get("jobs_path"), "results_paths": manifest.get("results_paths", []),
        "criteria": manifest.get("criteria", []), "excluded_criteria": manifest.get("excluded_criteria", []),
        "expected_interviews": manifest.get("expected_interviews"),
        "expected_answers": manifest.get("expected_answers"),
        "imported_answers": manifest.get("imported_answers", 0), "coverage": manifest.get("coverage"),
    } for path, manifest in assessments]

    blockers = []
    if missing_cells:
        blockers.append({
            "code": "missing_performance", "count": len(missing_cells),
            "sample_cells": [list(item) for item in missing_cells[:25]],
            "next_step": "mcda assessment build --id <assessment-id> --criteria <missing-criterion-ids>",
        })
    incomplete = [item["id"] for item in assessment_summaries if item["status"] != "complete"]
    if incomplete:
        blockers.append({
            "code": "incomplete_assessments", "assessment_ids": incomplete,
            "next_step": "ep run <jobs.ep> --output <results.ep>, then mcda assessment ingest <id> --results <results.ep>",
        })
    if not analyses:
        blockers.append({"code": "no_completed_analysis", "next_step": "mcda analyze run --method weighted-sum"})
    if primary_selection_problem:
        blockers.append({
            "code": primary_selection_problem, "selected_analysis_id": selected_id,
            "eligible_analysis_ids": [item["id"] for item in analysis_summaries if not item["participant_specific"]],
            "next_step": "mcda analyze primary set <analysis-id>",
        })
    if primary is not None and not primary.get("candidate_ranking"):
        blockers.append({"code": "no_candidate_ranking", "analysis_id": primary["id"]})
    references = [item for item in alternatives if item.get("type") == "reference"]
    if primary is not None and references and primary.get("reference_inclusive_ranking") is None:
        blockers.append({"code": "reference_inclusive_result_absent", "analysis_id": primary["id"]})

    warnings = []
    if not references:
        warnings.append({"code": "no_reference_alternative", "message": "No status-quo/reference comparison is defined."})
    if len(analyses) > 1:
        warnings.append({
            "code": "multiple_analyses", "message": "Use primary_analysis as canonical; treat other runs according to their roles.",
            "analysis_ids": [item["id"] for item in analysis_summaries],
        })
    if inferred_primary:
        warnings.append({
            "code": "legacy_primary_inferred",
            "message": "Exactly one eligible pooled analysis was inferred as primary; select it explicitly to record provenance.",
            "analysis_id": primary["id"], "next_step": f"mcda analyze primary set {primary['id']}",
        })
    if primary:
        warnings.extend(primary.get("warnings", []))

    next_steps = [item["next_step"] for item in blockers if item.get("next_step")]
    if not blockers:
        next_steps = ["Write writeup/report.md using this handoff and `mcda report template`."]
    return {
        "purpose": "Guidance for a calling coding agent that will write the final report.",
        "mcda_role": "MCDA records decision state, assessment artifacts, provenance, and analysis results. It does not write the final report.",
        "report_agent_role": "The calling agent interprets the evidence and authors the reader-facing narrative.",
        "target_file": "writeup/report.md", "ready_for_report_agent": not blockers,
        "blockers": blockers, "warnings": warnings,
        "available_evidence": {
            "project": {"path": _relative(project, meta_path), "id": meta.get("id"),
                        "title": meta.get("title"), "decision_question": meta.get("description")},
            "alternatives": {"path": ".mcda/alternatives/", "candidates": [a for a in alternatives if a.get("type") == "candidate"],
                             "references": references},
            "criteria": {"path": ".mcda/criteria/", "items": criteria},
            "participants": {"path": ".mcda/participants/", "items": participants},
            "weights": {"path": ".mcda/weights/", "raw_records": len(weights),
                        "resolved_in": primary["path"] if primary else None},
            "thresholds": {"path": ".mcda/thresholds/", "raw_records": len(thresholds),
                           "resolved_in": primary["path"] if primary else None},
            "performance": {"path": ".mcda/perf/", "raw_records": len(performance),
                            "latest_observed_cells": len(observed_cells), "expected_cells": len(expected_cells),
                            "missing_cells": len(missing_cells), "source_counts": dict(sorted(source_counts.items())),
                            "assessment_record_counts": dict(sorted(assessment_counts.items()))},
            "assessments": assessment_summaries, "analyses": analysis_summaries,
            "primary_selection": {"path": ".mcda/analysis_selections/", "events": len(primary_selections),
                                  "latest": primary_selections[-1][1] if primary_selections else None},
        },
        "decision_handoff": {
            "canonical_analysis_id": primary["id"] if primary else None,
            "canonical_analysis_path": primary["path"] if primary else None,
            "primary_analysis": primary, "current_analysis": primary,
            "robustness_analyses": [item for item in analysis_summaries
                                    if item["role"] in {"robustness", "sensitivity", "alternative-method"}],
            "analysis_history": [{"id": item["id"], "method": item["method"], "role": item["role"],
                                  "path": item["path"]}
                                 for item in analysis_summaries],
            "participant_specific_analyses": [
                {"id": item["id"], "method": item["method"], "path": item["path"],
                 "aggregation": item["aggregation"]}
                for item in analysis_summaries
                if item["participant_specific"]
            ],
        },
        "recommended_sections": SECTIONS, "writing_rules": WRITING_RULES,
        "study_layout": {
            "expected_context": "EP agent study directory under sessions/topic_<alias>/study_<letter>/",
            "report_assets": ["writeup/report.css", "writeup/report_header.tex", "writeup/fix-table-widths.lua",
                              "writeup/tables/", "writeup/plots/", "writeup/numbers/"],
            "report_rule": "Write the final narrative in the study writeup directory; do not ask MCDA to generate it.",
        },
        "next_steps": next_steps,
    }


@app.command("guide")
def guide(ctx: typer.Context) -> None:
    data = build_guide(ctx_project(ctx))
    output(ctx, data, warnings=data["warnings"], next_steps=data["next_steps"])


@app.command("template")
def template(ctx: typer.Context) -> None:
    guide_data = build_guide(ctx_project(ctx))
    current_path = guide_data["decision_handoff"]["canonical_analysis_path"] or "<complete an analysis>"
    lines = [
        "# <Decision title>", "", "<!-- Target: writeup/report.md -->", "",
        f"<!-- Canonical analysis: {current_path} -->", "",
    ]
    for section in SECTIONS:
        lines.extend([f"## {section}", "", "<!-- Add evidence-backed content; cite MCDA artifact paths/IDs. -->", ""])
    output(ctx, {
        "target_file": guide_data["target_file"], "ready_for_report_agent": guide_data["ready_for_report_agent"],
        "canonical_analysis_path": guide_data["decision_handoff"]["canonical_analysis_path"],
        "markdown": "\n".join(lines).rstrip() + "\n",
    }, warnings=guide_data["warnings"], next_steps=guide_data["next_steps"])
