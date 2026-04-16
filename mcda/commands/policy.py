from __future__ import annotations

import typer

from mcda.commands.common import ctx_project, output
from mcda.core.ids import local_iso_now, validate_id
from mcda.core.store import append_record, list_records

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("set")
def set_cmd(ctx: typer.Context, key: str, value: str, by: str = typer.Option(..., "--by"), rationale: str = "") -> None:
    project = ctx_project(ctx)
    validate_id(key.replace("-", "_"), "policy key")
    data = {"key": key, "value": value, "set_at": local_iso_now(), "set_by": by, "rationale": rationale}
    rid, _ = append_record(project, "policies", [key.replace("-", "_")], data)
    output(ctx, {"id": rid, **data})


@app.command("list")
def list_cmd(ctx: typer.Context) -> None:
    defaults = {
        "perf-missing": "exclude-participant",
        "perf-abstention": "exclude-participant",
        "weights-missing": "exclude-participant",
        "thresholds-missing": "exclude-participant",
    }
    for _, record in list_records(ctx_project(ctx), "policies"):
        defaults[record["key"]] = record["value"]
    output(ctx, defaults)
