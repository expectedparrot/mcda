from __future__ import annotations

import typer

from mcda.commands.common import ctx_project, output
from mcda.core.errors import UserError
from mcda.core.ids import local_iso_now, validate_id
from mcda.core.store import list_entities, read_entity, write_entity

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("add")
def add(
    ctx: typer.Context,
    crit_id: str,
    name: str,
    direction: str = typer.Option(..., "--direction"),
    unit: str = typer.Option(..., "--unit"),
    parent: str | None = typer.Option(None, "--parent"),
    description: str = "",
    edit: bool = False,
) -> None:
    if direction not in {"min", "max"}:
        raise UserError("Criterion direction must be min or max.", {"direction": direction})
    validate_id(crit_id, "criterion id")
    if parent:
        validate_id(parent, "parent criterion id")
    data = {
        "id": crit_id,
        "name": name,
        "direction": direction,
        "unit": unit,
        "parent": parent,
        "added_at": local_iso_now(),
        "description": description,
    }
    write_entity(ctx_project(ctx), "criteria", crit_id, data)
    output(ctx, data, human_message=f"Added criterion {crit_id}")


@app.command("add-group")
def add_group(
    ctx: typer.Context,
    crit_id: str,
    name: str,
    parent: str | None = typer.Option(None, "--parent"),
    description: str = "",
    edit: bool = False,
) -> None:
    validate_id(crit_id, "criterion id")
    if parent:
        validate_id(parent, "parent criterion id")
    data = {
        "id": crit_id,
        "name": name,
        "direction": None,
        "unit": None,
        "parent": parent,
        "added_at": local_iso_now(),
        "description": description,
    }
    write_entity(ctx_project(ctx), "criteria", crit_id, data)
    output(ctx, data, human_message=f"Added criterion group {crit_id}")


@app.command("list")
def list_cmd(ctx: typer.Context) -> None:
    output(ctx, list_entities(ctx_project(ctx), "criteria"))


@app.command("show")
def show(ctx: typer.Context, crit_id: str) -> None:
    output(ctx, read_entity(ctx_project(ctx), "criteria", crit_id))
