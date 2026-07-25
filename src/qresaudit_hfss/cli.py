import json
from contextlib import AbstractContextManager, nullcontext, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console

from qresaudit import __version__
from qresaudit.exceptions import BundleValidationError, HFSSSessionError, PreflightError
from qresaudit.models.common import Severity
from qresaudit.models.config import ProjectConfig
from qresaudit_hfss.exporter import export_bundle, load_config
from qresaudit_hfss.inspect import inspect_design, run_preflight
from qresaudit_hfss.session import open_hfss_session

app = typer.Typer(
    no_args_is_help=True,
    invoke_without_command=True,
    help="Inspect and export solved Ansys HFSS projects.",
)
console = Console()


def _quiet_vendor_output(enabled: bool) -> AbstractContextManager[object]:
    """Keep machine-readable CLI output free of PyAEDT startup messages."""
    return redirect_stdout(StringIO()) if enabled else nullcontext()


@app.callback()
def main(
    version: Annotated[bool, typer.Option("--version", help="Show the package version.")] = False,
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command()
def inspect(
    project: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    design: Annotated[str, typer.Option("--design", help="Exact AEDT design name.")],
    aedt_version: Annotated[str | None, typer.Option("--aedt-version")] = None,
    student: Annotated[bool, typer.Option("--student")] = False,
    graphical: Annotated[bool, typer.Option("--graphical")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        project_config = ProjectConfig(
            path=project,
            design=design,
            aedt_version=aedt_version,
            non_graphical=not (student or graphical),
            student_version=student,
        )
        with _quiet_vendor_output(json_output), open_hfss_session(project_config) as hfss:
            result = inspect_design(hfss)
        if json_output:
            typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))
        else:
            console.print(f"[bold]Project:[/bold] {result.project_name}")
            console.print(f"[bold]Design:[/bold] {result.design_name}")
            console.print(f"[bold]Solution:[/bold] {result.solution_type_raw}")
            console.print(f"[bold]Setups:[/bold] {', '.join(result.setups) or '-'}")
            console.print(
                f"[bold]Solved sweeps:[/bold] {', '.join(result.existing_analysis_sweeps) or '-'}"
            )
            console.print(f"[bold]Ports:[/bold] {', '.join(result.ports) or '-'}")
    except ValidationError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(2) from exc
    except HFSSSessionError as exc:
        console.print(f"[red]AEDT session failure:[/red] {exc}")
        raise typer.Exit(3) from exc


@app.command()
def export(
    project: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    config_path: Annotated[Path, typer.Option("--config", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output")],
    force: Annotated[bool, typer.Option("--force")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        config = load_config(config_path, project_override=project)
        if dry_run:
            payload = {
                "ok": project.is_file(),
                "scope": "static_configuration",
                "aedt_validated": False,
                "project": str(project),
                "design": config.project.design,
                "config": str(config_path),
            }
            if json_output:
                typer.echo(json.dumps(payload))
            else:
                console.print(
                    "[green]Static configuration check OK; AEDT was not opened[/green]"
                    if payload["ok"]
                    else "[red]Project missing[/red]"
                )
            if not payload["ok"]:
                raise typer.Exit(4)
            return
        with _quiet_vendor_output(json_output):
            result = export_bundle(config, output, force=force)
        if json_output:
            typer.echo(json.dumps({"ok": True, "bundle": str(result)}))
        else:
            console.print(f"[green]Bundle validated and published:[/green] {result}")
    except (ValidationError, ValueError) as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(2) from exc
    except HFSSSessionError as exc:
        console.print(f"[red]AEDT session failure:[/red] {exc}")
        raise typer.Exit(3) from exc
    except PreflightError as exc:
        console.print(f"[red]Preflight failure:[/red] {exc}")
        raise typer.Exit(4) from exc
    except BundleValidationError as exc:
        console.print(f"[red]Export validation failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    except Exception as exc:
        console.print(f"[red]Unexpected export failure:[/red] {exc}")
        raise typer.Exit(5) from exc


@app.command()
def preflight(
    project: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    config_path: Annotated[Path, typer.Option("--config", exists=True, dir_okay=False)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    try:
        config = load_config(config_path, project_override=project)
        with _quiet_vendor_output(json_output), open_hfss_session(config.project) as hfss:
            inspection = inspect_design(hfss)
            diagnostics = run_preflight(inspection, config)
        ok = not any(item.severity is Severity.ERROR for item in diagnostics)
        payload = {
            "ok": ok,
            "scope": "aedt_read_only_preflight",
            "aedt_validated": True,
            "project": str(config.project.path),
            "design": config.project.design,
            "diagnostics": [item.model_dump(mode="json") for item in diagnostics],
        }
        if json_output:
            typer.echo(json.dumps(payload))
        else:
            console.print(
                "[green]AEDT preflight passed[/green]" if ok else "[red]AEDT preflight failed[/red]"
            )
            for diagnostic in diagnostics:
                console.print(
                    f"{diagnostic.severity.value}: {diagnostic.code}: {diagnostic.message}"
                )
        raise typer.Exit(0 if ok else 4)
    except ValidationError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(2) from exc
    except HFSSSessionError as exc:
        console.print(f"[red]AEDT session failure:[/red] {exc}")
        raise typer.Exit(3) from exc
