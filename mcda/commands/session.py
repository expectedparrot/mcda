from __future__ import annotations

import typer

from mcda.commands.common import ctx_project, output
from mcda.core.errors import UserError
from mcda.core.ids import local_iso_now, validate_id
from mcda.core.store import list_entities, read_entity, write_entity, write_json

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("start")
def start(
    ctx: typer.Context,
    id_: str | None = typer.Option(None, "--id"),
    participants: list[str] = typer.Option(..., "--participants"),
    label: str = "",
) -> None:
    project = ctx_project(ctx)
    session_id = validate_id(id_ or f"session_{local_iso_now().replace('-', '').replace(':', '').replace('T', '_')}", "session id")
    lockfile = project.path(".current-session")
    if lockfile.exists():
        raise UserError("A session is already open.", {"session": lockfile.read_text(encoding="utf-8").strip()})
    for participant_id in participants:
        validate_id(participant_id, "participant id")
    data = {
        "id": session_id,
        "label": label,
        "started_at": local_iso_now(),
        "closed_at": None,
        "participants": participants,
        "results_shared": [],
        "notes": "",
    }
    write_entity(project, "sessions", session_id, data)
    lockfile.write_text(session_id, encoding="utf-8")
    output(ctx, data, human_message=f"Started session {session_id}")


@app.command("close")
def close(ctx: typer.Context, notes: str = "") -> None:
    project = ctx_project(ctx)
    lockfile = project.path(".current-session")
    if not lockfile.exists():
        raise UserError("No session is open.")
    session_id = lockfile.read_text(encoding="utf-8").strip()
    data = read_entity(project, "sessions", session_id)
    data["closed_at"] = local_iso_now()
    data["notes"] = notes
    write_json(project.path("sessions", f"{session_id}.json"), data)
    lockfile.unlink()
    output(ctx, data, human_message=f"Closed session {session_id}")


@app.command("status")
def status(ctx: typer.Context) -> None:
    project = ctx_project(ctx)
    lockfile = project.path(".current-session")
    if not lockfile.exists():
        output(ctx, {"open": False, "session": None})
        return
    session_id = lockfile.read_text(encoding="utf-8").strip()
    output(ctx, {"open": True, "session": read_entity(project, "sessions", session_id)})


@app.command("list")
def list_cmd(ctx: typer.Context) -> None:
    output(ctx, list_entities(ctx_project(ctx), "sessions"))
