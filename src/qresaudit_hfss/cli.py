import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console

from qresaudit.exceptions import BundleValidationError, HFSSSessionError, PreflightError
from qresaudit.models.config import ProjectConfig
from qresaudit_hfss.exporter import export_bundle, load_config
from qresaudit_hfss.inspect import inspect_design
from qresaudit_hfss.session import open_hfss_session

app = typer.Typer(no_args_is_help=True, help="Inspect and export solved Ansys HFSS projects.")
console = Console()


@app.command()
def inspect(
    project: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    design: Annotated[str | None, typer.Option("--design")] = None,
    aedt_version: Annotated[str | None, typer.Option("--aedt-version")] = None,
    student: Annotated[bool, typer.Option("--student")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    selected = design or project.stem
    try:
        project_config = ProjectConfig(
            path=project,
            design=selected,
            aedt_version=aedt_version,
            non_graphical=not student,
            student_version=student,
        )
        with open_hfss_session(project_config) as hfss:
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
) -> None:
    try:
        config = load_config(config_path, project_override=project)
        result = export_bundle(config, output, force=force)
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
