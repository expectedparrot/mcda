from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from mcda.cli import app

runner = CliRunner()


def run(args: list[str]) -> dict:
    result = runner.invoke(app, args, catch_exceptions=False, color=False, prog_name="mcda")
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def in_project(project: Path, args: list[str]) -> dict:
    return run(["-C", str(project), *args])


def create_complete_project(tmp_path: Path) -> Path:
    project = tmp_path / "report_project"
    run(["init", str(project), "--description", "Choose the strongest option."])
    in_project(project, ["alt", "add", "candidate_a", "Candidate A"])
    in_project(project, ["alt", "add", "candidate_b", "Candidate B"])
    in_project(project, ["alt", "add", "status_quo", "Status Quo", "--type", "reference"])
    in_project(project, ["crit", "add", "quality", "Quality", "--direction", "max", "--unit", "points"])
    in_project(project, ["participant", "add", "owner", "Decision Owner"])
    in_project(project, ["participant", "set-trait", "owner", "role", '"executive"'])
    in_project(project, ["weights", "set", "owner", "quality", "1"])
    for alternative, value, source in [
        ("candidate_a", "9", "audit"), ("candidate_b", "7", "audit"), ("status_quo", "5", "edsl"),
    ]:
        in_project(project, ["perf", "set", "owner", alternative, "quality", value, "--source", source])
    return project


def test_report_guide_complete_reference_project_is_deterministic(tmp_path: Path) -> None:
    project = create_complete_project(tmp_path)
    analyzed = in_project(project, ["analyze", "run", "--method", "weighted-sum"])
    assert analyzed["next_steps"][-1].endswith("report guide")

    before = sorted((path.relative_to(project), path.stat().st_mtime_ns) for path in project.rglob("*") if path.is_file())
    first = in_project(project, ["report", "guide"])
    second = in_project(project, ["report", "guide"])
    after = sorted((path.relative_to(project), path.stat().st_mtime_ns) for path in project.rglob("*") if path.is_file())
    assert first == second
    assert before == after
    data = first["data"]
    assert data["ready_for_report_agent"] is True
    assert data["target_file"] == "writeup/report.md"
    assert data["available_evidence"]["alternatives"]["candidates"][0]["id"] == "candidate_a"
    assert data["available_evidence"]["alternatives"]["references"][0]["id"] == "status_quo"
    assert data["available_evidence"]["performance"]["source_counts"] == {"audit": 2, "edsl": 1}
    assert data["decision_handoff"]["canonical_analysis_id"] == analyzed["data"]["id"]
    assert data["decision_handoff"]["canonical_analysis_path"].endswith(".json")
    assert data["study_layout"]["report_assets"]
    assert data["writing_rules"]
    assert in_project(project, ["next"])["data"]["recommendation"] == "mcda report guide"

    template = in_project(project, ["report", "template"])["data"]
    assert template["ready_for_report_agent"] is True
    assert "## Executive recommendation" in template["markdown"]
    assert "<Decision title>" in template["markdown"]
    assert "Candidate A is" not in template["markdown"]


def test_report_guide_incomplete_and_partial_assessment_blockers(tmp_path: Path) -> None:
    project = tmp_path / "incomplete"
    run(["init", str(project)])
    in_project(project, ["alt", "add", "candidate", "Candidate"])
    in_project(project, ["crit", "add", "quality", "Quality", "--direction", "max", "--unit", "points"])
    in_project(project, ["participant", "add", "owner", "Owner"])
    assessment_dir = project / ".mcda" / "assessments" / "round_1"
    assessment_dir.mkdir(parents=True)
    (assessment_dir / "manifest.json").write_text(json.dumps({
        "schema_version": 1, "id": "round_1", "status": "partial", "criteria": ["quality"],
        "excluded_criteria": [], "participants": ["owner"], "alternatives": ["candidate"],
        "jobs_path": str(assessment_dir / "jobs.ep"), "results_paths": [str(assessment_dir / "results.ep")],
        "expected_interviews": 1, "expected_answers": 1, "imported_answers": 0,
        "coverage": {"observed_answers": 0, "expected_answers": 1, "complete": False},
    }, indent=2) + "\n")
    data = in_project(project, ["report", "guide"])["data"]
    assert data["ready_for_report_agent"] is False
    assert {item["code"] for item in data["blockers"]} == {
        "missing_performance", "incomplete_assessments", "no_completed_analysis",
    }
    assert data["available_evidence"]["assessments"][0]["coverage"]["complete"] is False
    assert data["decision_handoff"]["canonical_analysis_id"] is None


def test_report_guide_electre_and_multiple_analyses(tmp_path: Path) -> None:
    project = create_complete_project(tmp_path)
    in_project(project, ["thresholds", "set", "owner", "quality", "--q", "0", "--p", "1", "--v", "4"])
    weighted = in_project(project, ["analyze", "run", "--method", "weighted-sum"])["data"]
    electre = in_project(project, ["analyze", "run", "--method", "electre-iii"])["data"]
    data = in_project(project, ["report", "guide"])["data"]
    assert data["ready_for_report_agent"] is True
    assert data["decision_handoff"]["canonical_analysis_id"] == weighted["id"]
    assert data["decision_handoff"]["primary_analysis"]["id"] == weighted["id"]
    assert [item["id"] for item in data["decision_handoff"]["analysis_history"]] == [weighted["id"], electre["id"]]
    assert data["decision_handoff"]["robustness_analyses"][0]["id"] == electre["id"]
    assert any(item["code"] == "multiple_analyses" for item in data["warnings"])


def test_capabilities_discovers_report_handoff() -> None:
    commands = run(["capabilities"])["data"]["commands"]
    assert "report guide" in commands
    assert "report template" in commands


def test_participant_runs_do_not_replace_primary_and_can_precede_it(tmp_path: Path) -> None:
    project = create_complete_project(tmp_path)
    participant_first = in_project(project, [
        "analyze", "run", "--method", "weighted-sum", "--participant", "owner",
    ])["data"]
    assert participant_first["role"] == "robustness"
    assert participant_first["canonical_analysis_id"] is None
    pooled = in_project(project, ["analyze", "run", "--method", "weighted-sum"])["data"]
    participant_after = in_project(project, [
        "analyze", "run", "--method", "weighted-sum", "--participant", "owner",
    ])["data"]
    guide = in_project(project, ["report", "guide"])["data"]
    assert guide["decision_handoff"]["canonical_analysis_id"] == pooled["id"]
    assert participant_after["canonical_analysis_id"] == pooled["id"]
    assert {item["id"] for item in guide["decision_handoff"]["participant_specific_analyses"]} == {
        participant_first["id"], participant_after["id"],
    }


def test_explicit_primary_promotion_and_missing_selection(tmp_path: Path) -> None:
    project = create_complete_project(tmp_path)
    first = in_project(project, ["analyze", "run", "--method", "weighted-sum"])["data"]
    second = in_project(project, [
        "analyze", "run", "--method", "weighted-sum", "--role", "exploratory",
    ])["data"]
    promoted = in_project(project, ["analyze", "primary", "set", second["id"]])["data"]
    assert promoted["selection"]["previous_analysis_id"] == first["id"]
    guide = in_project(project, ["report", "guide"])["data"]
    assert guide["decision_handoff"]["canonical_analysis_id"] == second["id"]
    assert in_project(project, ["report", "template"])["data"]["canonical_analysis_path"].endswith(f"{second['id']}.json")

    (project / ".mcda" / "results" / f"{second['id']}.json").unlink()
    broken = in_project(project, ["report", "guide"])["data"]
    assert broken["ready_for_report_agent"] is False
    assert "missing_selected_analysis" in {item["code"] for item in broken["blockers"]}


def test_legacy_primary_inference_and_ambiguity(tmp_path: Path) -> None:
    single = create_complete_project(tmp_path / "single")
    only = in_project(single, ["analyze", "run", "--method", "weighted-sum"])["data"]
    for path in (single / ".mcda" / "analysis_selections").glob("*.json"):
        path.unlink()
    inferred = in_project(single, ["report", "guide"])["data"]
    assert inferred["ready_for_report_agent"] is True
    assert inferred["decision_handoff"]["canonical_analysis_id"] == only["id"]
    assert any(item["code"] == "legacy_primary_inferred" for item in inferred["warnings"])

    ambiguous = create_complete_project(tmp_path / "ambiguous")
    in_project(ambiguous, ["analyze", "run", "--method", "weighted-sum"])
    in_project(ambiguous, ["analyze", "run", "--method", "weighted-sum"])
    for path in (ambiguous / ".mcda" / "analysis_selections").glob("*.json"):
        path.unlink()
    blocked = in_project(ambiguous, ["report", "guide"])["data"]
    assert blocked["ready_for_report_agent"] is False
    blocker = next(item for item in blocked["blockers"] if item["code"] == "ambiguous_primary")
    assert blocker["next_step"] == "mcda analyze primary set <analysis-id>"
