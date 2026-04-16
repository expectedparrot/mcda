from __future__ import annotations

from pathlib import Path

import typer

from mcda.commands.common import output
from mcda.core.ids import local_iso_now, validate_id
from mcda.core.project import create_project
from mcda.core.store import write_json


def command(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    description: str = typer.Option("", "--description"),
    edit: bool = typer.Option(False, "--edit", help="Reserved for future editor integration."),
) -> None:
    project_id = validate_id(Path(name).name, "project id")
    project = create_project(
        Path(name),
        {
            "id": project_id,
            "title": project_id.replace("_", " ").title(),
            "method": "electre-iii",
            "created_at": local_iso_now(),
            "description": description,
            "settings": {"lambda": 0.75},
        },
    )
    meta = {
        "id": project_id,
        "title": project_id.replace("_", " ").title(),
        "method": "electre-iii",
        "created_at": local_iso_now(),
        "description": description,
        "settings": {"lambda": 0.75},
    }
    write_json(project.path("meta.json"), meta)
    output(ctx, {"project": str(project.root), "data_dir": str(project.data_dir), "meta": meta}, human_message=f"Created {project.data_dir}")
