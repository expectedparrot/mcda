from __future__ import annotations

import typer

from mcda.commands.common import ctx_project, maybe_session, output
from mcda.core.ids import local_iso_now, validate_id
from mcda.core.store import append_record, list_records

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("set")
def set_cmd(
    ctx: typer.Context,
    participant_id: str,
    alternative_id: str,
    criterion_id: str,
    value: float,
    confidence: float = typer.Option(0.5, "--confidence"),
    source: str = typer.Option("unknown", "--source"),
    comment: str = "",
    reasoning: str = "",
) -> None:
    project = ctx_project(ctx)
    for value_id, label in [(participant_id, "participant id"), (alternative_id, "alternative id"), (criterion_id, "criterion id")]:
        validate_id(value_id, label)
    data = {
        "participant": participant_id,
        "alternative": alternative_id,
        "criterion": criterion_id,
        "value": value,
        "confidence": confidence,
        "recorded_at": local_iso_now(),
        "source": source,
        "comment": comment,
        "reasoning": reasoning,
    }
    session_id = maybe_session(project)
    if session_id:
        data["session"] = session_id
    rid, _ = append_record(project, "perf", [participant_id, alternative_id, criterion_id], data)
    output(ctx, {"id": rid, **data})


@app.command("abstain")
def abstain(ctx: typer.Context, participant_id: str, alternative_id: str, criterion_id: str, reason: str = typer.Option(..., "--reason")) -> None:
    project = ctx_project(ctx)
    data = {
        "participant": participant_id,
        "alternative": alternative_id,
        "criterion": criterion_id,
        "abstention": True,
        "recorded_at": local_iso_now(),
        "reason": reason,
    }
    session_id = maybe_session(project)
    if session_id:
        data["session"] = session_id
    rid, _ = append_record(project, "perf", [participant_id, alternative_id, criterion_id], data)
    output(ctx, {"id": rid, **data})


@app.command("show")
def show(ctx: typer.Context) -> None:
    output(ctx, [{"id": rid, **record} for rid, record in list_records(ctx_project(ctx), "perf")])
