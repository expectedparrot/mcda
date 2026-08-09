from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer

from mcda.core.project import Project, find_project


def ctx_project(ctx: typer.Context) -> Project:
    override: Path | None = ctx.obj.project if ctx.obj else None
    return find_project(override=override)


def output(
    ctx: typer.Context,
    data: Any,
    warnings: list[dict] | None = None,
    human_message: str | None = None,
    next_steps: list[str] | None = None,
) -> None:
    if ctx.obj and ctx.obj.human:
        if human_message:
            typer.echo(human_message)
        else:
            typer.echo(json.dumps(data, indent=2, sort_keys=True))
        return
    names = []
    cursor: typer.Context | None = ctx
    while cursor is not None:
        if cursor.info_name and cursor.info_name not in {"python", "python -m mcda.cli"}:
            names.append(cursor.info_name)
        cursor = cursor.parent
    names.reverse()
    if not names or names[0] != "mcda":
        names.insert(0, "mcda")
    command_path = " ".join(names)
    payload = {
        "schema_version": "1.0",
        "command": command_path,
        "status": "ok",
        "argv": ["mcda", *sys.argv[1:]],
        "data": data if data is not None else {},
        "warnings": warnings or [],
        "errors": [],
        "next_steps": next_steps or [],
    }
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def maybe_session(project: Project) -> str | None:
    path = project.path(".current-session")
    if not path.exists():
        return None
    session_id = path.read_text(encoding="utf-8").strip()
    return session_id or None
