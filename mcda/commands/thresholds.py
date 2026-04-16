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
    q: float = typer.Option(..., "--q"),
    p: float = typer.Option(..., "--p"),
    v: float | None = typer.Option(None, "--v"),
    no_veto: bool = typer.Option(False, "--no-veto"),
    q_confidence: float = typer.Option(0.5, "--q-confidence"),
    p_confidence: float = typer.Option(0.5, "--p-confidence"),
    v_confidence: float = typer.Option(0.5, "--v-confidence"),
    comment: str = "",
) -> None:
    project = ctx_project(ctx)
    validate_id(participant_id, "participant id")
    validate_id(criterion_id, "criterion id")
    data = {
        "participant": participant_id,
        "criterion": criterion_id,
        "recorded_at": local_iso_now(),
        "comment": comment,
        "q": {"value": q, "confidence": q_confidence, "reasoning": ""},
        "p": {"value": p, "confidence": p_confidence, "reasoning": ""},
        "v": None if no_veto else {"value": v, "confidence": v_confidence, "reasoning": ""},
    }
    session_id = maybe_session(project)
    if session_id:
        data["session"] = session_id
    rid, _ = append_record(project, "thresholds", [participant_id, criterion_id], data)
    output(ctx, {"id": rid, **data})


@app.command("show")
def show(ctx: typer.Context) -> None:
    output(ctx, [{"id": rid, **record} for rid, record in list_records(ctx_project(ctx), "thresholds")])
