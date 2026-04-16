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
    criterion_id: str,
    value: float,
    confidence: float = typer.Option(0.5, "--confidence"),
    method: str = typer.Option("direct", "--method"),
    comment: str = "",
    reasoning: str = "",
) -> None:
    project = ctx_project(ctx)
    validate_id(participant_id, "participant id")
    validate_id(criterion_id, "criterion id")
    data = {
        "participant": participant_id,
        "criterion": criterion_id,
        "value": value,
        "confidence": confidence,
        "recorded_at": local_iso_now(),
        "elicitation_method": method,
        "comment": comment,
        "reasoning": reasoning,
    }
    session_id = maybe_session(project)
    if session_id:
        data["session"] = session_id
    rid, _ = append_record(project, "weights", [participant_id, criterion_id], data)
    output(ctx, {"id": rid, **data})


@app.command("show")
def show(ctx: typer.Context) -> None:
    output(ctx, [{"id": rid, **record} for rid, record in list_records(ctx_project(ctx), "weights")])
