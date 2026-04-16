from __future__ import annotations

import json

import typer

from mcda.commands.common import ctx_project, output
from mcda.core.ids import local_iso_now, validate_id
from mcda.core.store import list_entities, read_entity, write_entity, write_json

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("add")
def add(ctx: typer.Context, participant_id: str, name: str, bio: str = "", edit: bool = False) -> None:
    project = ctx_project(ctx)
    validate_id(participant_id, "participant id")
    data = {
        "id": participant_id,
        "name": name,
        "added_at": local_iso_now(),
        "bio": bio,
        "traits": {},
        "scope": {"may_weight": True, "may_evaluate": None, "may_set_thresholds": None},
    }
    write_entity(project, "participants", participant_id, data)
    output(ctx, data, human_message=f"Added participant {participant_id}")


@app.command("list")
def list_cmd(ctx: typer.Context) -> None:
    output(ctx, list_entities(ctx_project(ctx), "participants"))


@app.command("show")
def show(ctx: typer.Context, participant_id: str) -> None:
    output(ctx, read_entity(ctx_project(ctx), "participants", participant_id))


@app.command("set-trait")
def set_trait(ctx: typer.Context, participant_id: str, key: str, value: str) -> None:
    validate_id(key, "trait key")
    project = ctx_project(ctx)
    data = read_entity(project, "participants", participant_id)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = value
    if not isinstance(parsed, (str, int, float, bool)) and parsed is not None:
        raise typer.BadParameter("Trait values must be JSON primitives.")
    data.setdefault("traits", {})[key] = parsed
    write_json(project.path("participants", f"{participant_id}.json"), data)
    output(ctx, data, human_message=f"Set trait {key} for {participant_id}")


@app.command("set-scope")
def set_scope(
    ctx: typer.Context,
    participant_id: str,
    may_weight: bool | None = typer.Option(None, "--may-weight"),
) -> None:
    project = ctx_project(ctx)
    data = read_entity(project, "participants", participant_id)
    if may_weight is not None:
        data.setdefault("scope", {})["may_weight"] = may_weight
    write_json(project.path("participants", f"{participant_id}.json"), data)
    output(ctx, data)
