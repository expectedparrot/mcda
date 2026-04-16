from __future__ import annotations

import typer

from mcda.commands.common import ctx_project, output
from mcda.core.errors import UserError
from mcda.core.ids import local_iso_now, validate_id
from mcda.core.store import list_entities, read_entity, write_entity, write_json

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("add")
def add(
    ctx: typer.Context,
    alt_id: str,
    name: str,
    type_: str = typer.Option("candidate", "--type"),
    description: str = "",
    edit: bool = False,
) -> None:
    project = ctx_project(ctx)
    validate_id(alt_id, "alternative id")
    if type_ not in {"candidate", "reference"}:
        raise UserError("Alternative type must be candidate or reference.", {"type": type_})
    data = {"id": alt_id, "name": name, "type": type_, "added_at": local_iso_now(), "description": description}
    write_entity(project, "alternatives", alt_id, data)
    output(ctx, data, human_message=f"Added alternative {alt_id}")


@app.command("list")
def list_cmd(ctx: typer.Context, type_: str = typer.Option("all", "--type")) -> None:
    items = list_entities(ctx_project(ctx), "alternatives")
    if type_ != "all":
        items = [item for item in items if item.get("type") == type_]
    output(ctx, items)


@app.command("show")
def show(ctx: typer.Context, alt_id: str) -> None:
    output(ctx, read_entity(ctx_project(ctx), "alternatives", alt_id))


@app.command("tag")
def tag(ctx: typer.Context, alt_id: str, as_: str = typer.Option(..., "--as")) -> None:
    if as_ not in {"candidate", "reference"}:
        raise UserError("Alternative type must be candidate or reference.", {"type": as_})
    project = ctx_project(ctx)
    data = read_entity(project, "alternatives", alt_id)
    data["type"] = as_
    write_json(project.path("alternatives", f"{alt_id}.json"), data)
    output(ctx, data)
