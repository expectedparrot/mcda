from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from mcda.core.project import Project, find_project


def ctx_project(ctx: typer.Context) -> Project:
    override: Path | None = ctx.obj.project if ctx.obj else None
    return find_project(override=override)


def output(ctx: typer.Context, data: Any, warnings: list[dict] | None = None, human_message: str | None = None) -> None:
    if ctx.obj and ctx.obj.human:
        if human_message:
            typer.echo(human_message)
        else:
            typer.echo(json.dumps(data, indent=2, sort_keys=True))
        return
    typer.echo(json.dumps({"data": data, "warnings": warnings or []}, indent=2, sort_keys=True))


def maybe_session(project: Project) -> str | None:
    path = project.path(".current-session")
    if not path.exists():
        return None
    session_id = path.read_text(encoding="utf-8").strip()
    return session_id or None
