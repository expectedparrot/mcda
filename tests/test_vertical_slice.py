from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mcda.cli import app

runner = CliRunner()


def run_cmd(args: list[str], cwd: Path | None = None) -> dict:
    result = runner.invoke(app, args, catch_exceptions=False, env={}, color=False, prog_name="mcda", obj=None)
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def run_project(args: list[str], project: Path) -> dict:
    return run_cmd(["--project", str(project), *args])


def test_init_creates_mcda(tmp_path: Path) -> None:
    project = tmp_path / "office_lease_selection"
    data = run_cmd(["init", str(project), "--description", "Select office lease."])
    assert Path(data["data"]["data_dir"]) == project / ".mcda"
    assert (project / ".mcda" / "meta.json").exists()
    assert not (project / "meta.json").exists()
    info = run_project(["info"], project)["data"]
    assert info["project"] == str(project.resolve())
    assert info["counts"]["alternatives"] == 0


def test_agent_envelope_and_next(tmp_path: Path) -> None:
    project = tmp_path / "agent_project"
    created = run_cmd(["init", str(project)])
    assert set(created) == {
        "schema_version", "command", "status", "argv", "data", "warnings", "errors", "next_steps"
    }
    recommendation = run_project(["next"], project)
    assert recommendation["status"] == "ok"
    assert recommendation["data"]["recommendation"].startswith("mcda alt add")
    assert recommendation["next_steps"]


def test_assessment_builds_loadable_edsl_jobs(tmp_path: Path) -> None:
    edsl = pytest.importorskip("edsl")
    project = tmp_path / "agent_assessment"
    run_cmd(["init", str(project)])
    run_project(["alt", "add", "option_a", "Option A"], project)
    run_project(["crit", "add", "quality", "Quality", "--direction", "max", "--unit", "points"], project)
    run_project(["participant", "add", "reviewer", "Reviewer"], project)
    built = run_project(["assessment", "build", "--id", "round_1"], project)
    jobs_path = Path(built["data"]["jobs_path"])
    assert jobs_path.exists()
    assert built["data"]["expected_answers"] == 1
    assert edsl.Jobs.git.load(str(jobs_path)) is not None
    assert built["next_steps"][0].startswith("ep run ")


def test_assessment_subset_ingests_flattened_real_edsl_results_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    edsl = pytest.importorskip("edsl")
    project = tmp_path / "live_run_regression"
    run_cmd(["init", str(project)])
    for alt_id in ["option_a", "option_b"]:
        run_project(["alt", "add", alt_id, alt_id.replace("_", " ").title()], project)
    for args in [
        ["crit", "add", "cost", "Cost", "--direction", "min", "--unit", "USD"],
        ["crit", "add", "quality", "Quality", "--direction", "max", "--unit", "points"],
        ["crit", "add", "risk", "Risk", "--direction", "min", "--unit", "points"],
    ]:
        run_project(args, project)
    for participant in ["alice", "bob"]:
        run_project(["participant", "add", participant, participant.title()], project)
        for criterion in ["cost", "quality", "risk"]:
            run_project(["weights", "set", participant, criterion, "1"], project)
        for alternative, value in [("option_a", "100"), ("option_b", "120")]:
            run_project(["perf", "set", participant, alternative, "cost", value, "--source", "invoice"], project)

    built = run_project([
        "assessment", "build", "--id", "subjective", "--criteria", "quality,risk",
    ], project)["data"]
    assert built["criteria"] == ["quality", "risk"]
    assert built["excluded_criteria"] == ["cost"]
    assert built["expected_answers"] == 8

    jobs = edsl.Jobs.git.load(built["jobs_path"])

    def answer(self, question, scenario):
        base = 8 if scenario["alternative_id"] == "option_a" else 4
        return base if question.question_name == "quality" else 10 - base

    for agent in jobs.agents:
        agent.add_direct_question_answering_method(answer)
    from edsl.language_models import LanguageModel
    from edsl.object_store.store import ObjectStore
    monkeypatch.setattr(ObjectStore, "default_root", staticmethod(lambda: tmp_path / "edsl_objects"))
    jobs = edsl.Jobs(
        survey=jobs.survey, agents=jobs.agents, scenarios=jobs.scenarios,
        models=[LanguageModel.example(test_model=True)],
    )
    results = jobs.run(cache=False, disable_remote_inference=True)
    results_path = project / ".mcda" / "assessments" / "subjective" / "results.ep"
    results.git.save(str(results_path), message="Create flattened Results ingestion fixture")
    loaded_rows = edsl.Results.git.load(str(results_path)).to_dicts()
    assert "quality" in loaded_rows[0]
    assert "answer.quality" not in loaded_rows[0]

    ingested = run_project([
        "assessment", "ingest", "subjective", "--results", str(results_path),
    ], project)["data"]
    assert ingested["imported_answers"] == 8
    assert ingested["coverage"]["complete"] is True
    assert len(run_project(["perf", "show"], project)["data"]) == 12
    assert run_project(["next"], project)["data"]["recommendation"].startswith("mcda analyze run")

    replay = runner.invoke(app, [
        "--project", str(project), "assessment", "ingest", "subjective", "--results", str(results_path),
    ])
    assert replay.exit_code == 1
    assert len(run_project(["perf", "show"], project)["data"]) == 12


def test_assessment_rejects_partial_rows_without_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mcda.commands import assessment

    project = tmp_path / "partial"
    run_cmd(["init", str(project)])
    run_project(["alt", "add", "option_a", "Option A"], project)
    run_project(["crit", "add", "quality", "Quality", "--direction", "max", "--unit", "points"], project)
    run_project(["participant", "add", "alice", "Alice"], project)
    built = run_project(["assessment", "build", "--id", "round_1"], project)["data"]
    partial_path = project / "partial.ep"
    partial_path.touch()

    class PartialResults:
        class git:
            @staticmethod
            def load(path):
                return PartialResults()

        def to_dicts(self):
            return [{"participant_id": "alice", "alternative_id": "option_a"}]

    original = assessment._edsl
    monkeypatch.setattr(assessment, "_edsl", lambda: (*original()[:4], PartialResults, *original()[5:]))
    result = runner.invoke(app, [
        "--project", str(project), "assessment", "ingest", "round_1", "--results", str(partial_path),
    ])
    assert result.exit_code == 1
    assert not list((project / ".mcda" / "perf").glob("*.json"))
    manifest = json.loads(Path(built["manifest_path"]).read_text())
    assert manifest["results_paths"] == []


def test_id_validation_rejects_hyphen(tmp_path: Path) -> None:
    project = tmp_path / "office_lease_selection"
    run_cmd(["init", str(project)])
    result = runner.invoke(app, ["--project", str(project), "alt", "add", "downtown-loft", "Downtown Loft"])
    assert result.exit_code == 1
    assert result.exception is not None
    assert "Invalid alternative id" in str(result.exception)


def test_session_stamps_records(tmp_path: Path) -> None:
    project = tmp_path / "office_lease_selection"
    run_cmd(["init", str(project)])
    run_project(["participant", "add", "alice", "Alice Rivera"], project)
    started = run_project(["session", "start", "--id", "round_1", "--participants", "alice"], project)["data"]
    assert started["id"] == "round_1"
    run_project(["crit", "add", "quality", "Quality", "--direction", "max", "--unit", "score"], project)
    record = run_project(["weights", "set", "alice", "quality", "1"], project)["data"]
    assert record["session"] == "round_1"
    closed = run_project(["session", "close", "--notes", "done"], project)["data"]
    assert closed["closed_at"] is not None
    assert not (project / ".mcda" / ".current-session").exists()


def test_weighted_sum_does_not_require_thresholds(tmp_path: Path) -> None:
    project = tmp_path / "vendor_selection"
    run_cmd(["init", str(project)])
    run_project(["participant", "add", "ops", "Operations Lead"], project)
    run_project(["alt", "add", "balanced_vendor", "Balanced Vendor", "--type", "candidate"], project)
    run_project(["alt", "add", "budget_vendor", "Budget Vendor", "--type", "candidate"], project)
    run_project(["crit", "add", "annual_cost", "Annual cost", "--direction", "min", "--unit", "thousands USD"], project)
    run_project(["crit", "add", "security", "Security", "--direction", "max", "--unit", "score"], project)
    run_project(["weights", "set", "ops", "annual_cost", "20"], project)
    run_project(["weights", "set", "ops", "security", "80"], project)
    run_project(["perf", "set", "ops", "balanced_vendor", "annual_cost", "115"], project)
    run_project(["perf", "set", "ops", "balanced_vendor", "security", "94"], project)
    run_project(["perf", "set", "ops", "budget_vendor", "annual_cost", "80"], project)
    run_project(["perf", "set", "ops", "budget_vendor", "security", "74"], project)

    result = run_project(["analyze", "run", "--method", "weighted-sum"], project)["data"]
    assert result["method"] == "weighted-sum"
    assert result["resolved_thresholds"] == {}
    assert result["candidate_ranking"][0]["alternatives"] == ["balanced_vendor"]
    assert result["scores"]["balanced_vendor"] > result["scores"]["budget_vendor"]


def test_office_lease_vertical_slice(tmp_path: Path) -> None:
    project = tmp_path / "office_lease_selection"
    run_cmd(["init", str(project), "--description", "Select the best office lease."])

    for pid, name in [("alice", "Alice Rivera"), ("bob", "Bob Chen"), ("carol", "Carol Singh")]:
        run_project(["participant", "add", pid, name], project)

    for args in [
        ["alt", "add", "downtown_loft", "Downtown Loft", "--type", "candidate"],
        ["alt", "add", "midtown_suite", "Midtown Suite", "--type", "candidate"],
        ["alt", "add", "suburban_campus", "Suburban Campus", "--type", "candidate"],
        ["alt", "add", "current_office", "Current Office", "--type", "reference"],
    ]:
        run_project(args, project)

    for args in [
        ["crit", "add-group", "financial", "Financial"],
        ["crit", "add", "annual_cost", "Annual cost", "--direction", "min", "--unit", "thousands USD per year", "--parent", "financial"],
        ["crit", "add", "commute_time", "Commute time", "--direction", "min", "--unit", "average minutes"],
        ["crit", "add", "space_quality", "Space quality", "--direction", "max", "--unit", "score 0-100"],
        ["crit", "add", "lease_flexibility", "Lease flexibility", "--direction", "max", "--unit", "score 0-100"],
    ]:
        run_project(args, project)

    weights = {
        "alice": {"financial": 30, "commute_time": 25, "space_quality": 30, "lease_flexibility": 15, "annual_cost": 1},
        "bob": {"financial": 20, "commute_time": 35, "space_quality": 30, "lease_flexibility": 15, "annual_cost": 1},
        "carol": {"financial": 40, "commute_time": 20, "space_quality": 25, "lease_flexibility": 15, "annual_cost": 1},
    }
    for participant, entries in weights.items():
        for criterion, value in entries.items():
            run_project(["weights", "set", participant, criterion, str(value)], project)

    thresholds = {
        "annual_cost": ["25", "75", "175"],
        "commute_time": ["3", "8", "20"],
        "space_quality": ["5", "15", "35"],
    }
    for participant in weights:
        for criterion, (q, p, v) in thresholds.items():
            run_project(["thresholds", "set", participant, criterion, "--q", q, "--p", p, "--v", v], project)
        run_project(["thresholds", "set", participant, "lease_flexibility", "--q", "5", "--p", "15", "--no-veto"], project)

    perf = {
        "downtown_loft": {"annual_cost": 620, "commute_time": 28, "space_quality": 92, "lease_flexibility": 55},
        "midtown_suite": {"annual_cost": 500, "commute_time": 35, "space_quality": 80, "lease_flexibility": 70},
        "suburban_campus": {"annual_cost": 390, "commute_time": 52, "space_quality": 72, "lease_flexibility": 88},
        "current_office": {"annual_cost": 540, "commute_time": 38, "space_quality": 68, "lease_flexibility": 45},
    }
    for participant in weights:
        for alternative, entries in perf.items():
            for criterion, value in entries.items():
                run_project(["perf", "set", participant, alternative, criterion, str(value), "--confidence", "1"], project)

    result = run_project(["analyze", "run"], project)["data"]
    assert result["resolved_weights"] == {
        "annual_cost": 0.3,
        "commute_time": 0.25,
        "lease_flexibility": 0.15,
        "space_quality": 0.3,
    }
    assert "current_office" not in {
        alternative
        for rank in result["candidate_ranking"]
        for alternative in rank["alternatives"]
    }
    assert "current_office" in {
        alternative
        for rank in result["reference_ranking"]
        for alternative in rank["alternatives"]
    }
    assert list((project / ".mcda" / "weights").glob("*.json"))
