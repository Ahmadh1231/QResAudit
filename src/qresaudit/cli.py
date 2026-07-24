import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from qresaudit import __version__
from qresaudit.models.config import ExportConfig
from qresaudit.models.manifest import HFSSRunManifest
from qresaudit.validation.engine import ValidationResult, validate_bundle

app = typer.Typer(
    no_args_is_help=True,
    invoke_without_command=True,
    help="Inspect and validate portable HFSS result bundles.",
)
console = Console()


@app.callback()
def main(
    version: Annotated[bool, typer.Option("--version", help="Show the package version.")] = False,
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


def _render(result: ValidationResult, json_output: bool) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "valid": result.valid,
                    "diagnostics": [item.model_dump(mode="json") for item in result.diagnostics],
                },
                indent=2,
            )
        )
        return
    table = Table("Severity", "Code", "Path", "Message")
    for item in result.diagnostics:
        table.add_row(item.severity.value, item.code, item.path or "", item.message)
    if result.diagnostics:
        console.print(table)
    console.print("[green]VALID[/green]" if result.valid else "[red]INVALID[/red]")


@app.command()
def validate(
    bundle: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    strict: Annotated[bool, typer.Option("--strict/--no-strict")] = True,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    result = validate_bundle(bundle, strict=strict)
    _render(result, json_output)
    raise typer.Exit(code=0 if result.valid else 1)


@app.command()
def show(bundle: Annotated[Path, typer.Argument(exists=True, file_okay=False)]) -> None:
    manifest = HFSSRunManifest.model_validate_json(
        (bundle / "manifest.json").read_text(encoding="utf-8")
    )
    console.print_json(data=manifest.model_dump(mode="json"))


@app.command("schema")
def schema_command(
    model: Annotated[str, typer.Argument(help="manifest or config")],
) -> None:
    if model == "manifest":
        schema = HFSSRunManifest.model_json_schema()
    elif model == "config":
        schema = ExportConfig.model_json_schema()
    else:
        raise typer.BadParameter("model must be 'manifest' or 'config'")
    typer.echo(json.dumps(schema, indent=2))
