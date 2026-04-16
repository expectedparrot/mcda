from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from .commands import alt, analyze, crit, info, init, participant, perf, policy, session, thresholds, weights
from .core.errors import McdaError

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


class CliContext:
    def __init__(self, project: Path | None, human: bool, quiet: bool):
        self.project = project
        self.human = human
        self.quiet = quiet


def emit(data: Any = None, warnings: list[dict] | None = None) -> None:
    payload = {"data": data, "warnings": warnings or []}
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


def emit_human(message: str) -> None:
    console.print(message)


@app.callback()
def callback(
    ctx: typer.Context,
    project: Path | None = typer.Option(None, "--project", help="Override project root."),
    human: bool = typer.Option(False, "--human", help="Use human-readable output."),
    quiet: bool = typer.Option(False, "--quiet", help="Suppress non-data human output."),
) -> None:
    ctx.obj = CliContext(project=project, human=human, quiet=quiet)


app.command("init")(init.command)
app.command("info")(info.command)
app.add_typer(participant.app, name="participant")
app.add_typer(alt.app, name="alt")
app.add_typer(crit.app, name="crit")
app.add_typer(weights.app, name="weights")
app.add_typer(thresholds.app, name="thresholds")
app.add_typer(perf.app, name="perf")
app.add_typer(policy.app, name="policy")
app.add_typer(session.app, name="session")
app.add_typer(analyze.app, name="analyze")


def main() -> None:
    try:
        app()
    except McdaError as exc:
        typer.echo(
            json.dumps(
                {"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
                indent=2,
                sort_keys=True,
            ),
            err=True,
        )
        sys.exit(exc.exit_code)
    except Exception as exc:
        typer.echo(
            json.dumps(
                {"error": {"code": "internal_error", "message": str(exc), "details": {}}},
                indent=2,
                sort_keys=True,
            ),
            err=True,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
