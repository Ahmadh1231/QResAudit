"""QResAudit CLI — portable validation, analysis, and audit of HFSS evidence bundles."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from qresaudit import __version__
from qresaudit.adapters import ADAPTERS
from qresaudit.analysis.audit import audit_bundle, write_audit_output
from qresaudit.analysis.compare import compare_bundles
from qresaudit.analysis.convergence import (
    audit_convergence,
    convergence_summary_json,
    convergence_to_dataframe,
)
from qresaudit.analysis.field_integration import (
    integrate_bundle_fields,
)
from qresaudit.analysis.fitting import fit_bundle_resonator
from qresaudit.analysis.mode_tracking import track_modes
from qresaudit.analysis.optimization import bayesian_optimization
from qresaudit.analysis.participation import compute_participation_bundle
from qresaudit.analysis.spin_resonator import (
    SpinSampleConfig,
    analyze_spin_coupling,
    sweep_parameter,
)
from qresaudit.diagnosis import answer_query
from qresaudit.diagnosis import diagnose as diagnose_data
from qresaudit.digital_twin import calibrate_resonator
from qresaudit.geometry import make_cpw_design, write_portable_spec
from qresaudit.knowledge import KnowledgeBase
from qresaudit.loop import SimulationLoop
from qresaudit.models.config import ExportConfig
from qresaudit.models.manifest import HFSSRunManifest
from qresaudit.multiphysics import (
    strain_frequency_shift,
    thermal_frequency_shift,
)
from qresaudit.planner import plan_design
from qresaudit.report import build_design_report, write_design_report
from qresaudit.schema_migrate import migrate_bundle
from qresaudit.validation.engine import ValidationResult, validate_bundle

app = typer.Typer(
    no_args_is_help=True,
    invoke_without_command=True,
    help="Portable HFSS evidence validation, analysis, and audit.",
)
console = Console()


@app.command("diagnose-data")
def diagnose_data_command(
    input_json: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    query: Annotated[str | None, typer.Option("--query")] = None,
) -> None:
    """Run deterministic v2 diagnosis on a JSON evidence summary."""
    data = json.loads(input_json.read_text(encoding="utf-8"))
    findings = diagnose_data(data)
    if query:
        typer.echo(answer_query(findings, query))
    else:
        typer.echo(json.dumps([f.__dict__ for f in findings], indent=2))


@app.command("import-manifest")
def import_manifest(
    solver: Annotated[
        str, typer.Argument(help="hfss, palace, comsol, cst, sonnet, openems, or elmer")
    ],
    source: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
) -> None:
    """Import a portable solver bundle without running a solver."""
    if solver not in ADAPTERS:
        raise typer.BadParameter(f"unsupported adapter: {solver}")
    manifest = ADAPTERS[solver].import_bundle(source)
    typer.echo(manifest.model_dump_json(indent=2))


# ── Top-level flags ────────────────────────────────────────────────────


@app.callback()
def main(
    version: Annotated[bool, typer.Option("--version", help="Show the package version.")] = False,
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


# ── Rendering helpers ──────────────────────────────────────────────────


def _render(result: ValidationResult, json_output: bool) -> None:
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "valid": result.valid,
                    "diagnostics": [d.model_dump(mode="json") for d in result.diagnostics],
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


def _json_or_print(data: object, json_output: bool) -> None:
    if json_output:
        if hasattr(data, "model_dump"):
            typer.echo(json.dumps(data.model_dump(mode="json"), indent=2, default=str))
        else:
            typer.echo(json.dumps(data, indent=2, default=str))
    else:
        console.print(data)


# ── Phase 1 commands (v0.1.1) ──────────────────────────────────────────


@app.command()
def validate(
    bundle: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    strict: Annotated[bool, typer.Option("--strict/--no-strict")] = True,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Validate a bundle directory."""
    result = validate_bundle(bundle, strict=strict)
    _render(result, json_output)
    raise typer.Exit(code=0 if result.valid else 1)


@app.command()
def show(bundle: Annotated[Path, typer.Argument(exists=True, file_okay=False)]) -> None:
    """Show the manifest of a bundle."""
    manifest = HFSSRunManifest.model_validate_json(
        (bundle / "manifest.json").read_text(encoding="utf-8")
    )
    console.print_json(data=manifest.model_dump(mode="json"))


@app.command("schema")
def schema_command(
    model: Annotated[str, typer.Argument(help="manifest or config")],
) -> None:
    """Emit the JSON Schema for a model."""
    if model == "manifest":
        schema = HFSSRunManifest.model_json_schema()
    elif model == "config":
        schema = ExportConfig.model_json_schema()
    else:
        raise typer.BadParameter("model must be 'manifest' or 'config'")
    typer.echo(json.dumps(schema, indent=2))


@app.command()
def migrate(
    bundle: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    to_schema: Annotated[str, typer.Option("--to-schema")] = "0.2.0",
) -> None:
    """Migrate a bundle to a newer schema version."""
    result = migrate_bundle(bundle, to_schema=to_schema)
    console.print(f"[green]Migrated to {to_schema}:[/green] {result}")


# ── Phase 2: Convergence ───────────────────────────────────────────────


@app.command()
def convergence(
    bundle: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Audit adaptive-pass convergence evidence."""
    diag = audit_convergence(bundle)
    if output:
        output.mkdir(parents=True, exist_ok=True)
        (output / "convergence.json").write_text(
            json.dumps(convergence_summary_json(diag), indent=2) + "\n", encoding="utf-8"
        )
        convergence_to_dataframe(diag).to_csv(output / "convergence.csv", index=False)
        console.print(f"[green]Saved to {output}[/green]")
    if json_output:
        typer.echo(json.dumps(convergence_summary_json(diag), indent=2))
    else:
        console.print(f"Passes: {diag.total_passes} | Converged: {diag.is_converged}")
        console.print(
            f"Final max_delta_S: {diag.final_max_delta_s} | "
            f"False conv risk: {diag.false_convergence_risk}"
        )
        console.print(
            f"Extrapolated f0: {diag.limiting_value_extrapolation_hz} "
            f"+/- {diag.limiting_value_uncertainty_hz}"
        )


# ── Phase 2: Resonator Fitting ─────────────────────────────────────────


@app.command()
def fit(
    bundle: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    response: Annotated[str, typer.Option("--response", "-r")] = "S21",
    model: Annotated[str, typer.Option("--model", "-m")] = "notch",
    f0_guess: Annotated[float | None, typer.Option("--f0-guess")] = None,
    ql_guess: Annotated[float, typer.Option("--ql-guess")] = 1000.0,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Fit a resonator model to Touchstone data."""
    result = fit_bundle_resonator(
        bundle,
        response=response,
        model=model,
        f0_guess=f0_guess,
        ql_guess=ql_guess,
    )
    if json_output:
        typer.echo(json.dumps(result.model_dump(mode="json"), indent=2, default=str))
    else:
        console.print(
            f"[bold]f0:[/bold] {result.f0_hz / 1e9:.6f} GHz "
            f"+/- {result.f0_uncertainty_hz / 1e6:.3f} MHz"
        )
        console.print(
            f"[bold]Ql:[/bold] {result.q_loaded:.1f} +/- {result.q_loaded_uncertainty:.1f}"
        )
        console.print(f"[bold]|Qc|:[/bold] {result.q_coupling_absolute:.1f}")
        console.print(f"[bold]Qi:[/bold] {result.q_internal or float('nan'):.1f}")
        console.print(f"[bold]RMS residual:[/bold] {result.residual_rms:.6f}")


# ── Phase 2: Mode Tracking ─────────────────────────────────────────────

mode_app = typer.Typer(no_args_is_help=True, help="Eigenmode analysis commands.")
app.add_typer(mode_app, name="modes")


@mode_app.command("track")
def mode_track(
    sweep_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    field_pattern: Annotated[str, typer.Option("--pattern")] = "mode_*_E.h5",
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Track eigenmodes across a parameter sweep directory."""
    branches, crossings = track_modes(sweep_dir, field_pattern=field_pattern)
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "branches": [b.model_dump(mode="json") for b in branches],
                    "crossings": [c.model_dump(mode="json") for c in crossings],
                },
                indent=2,
            )
        )
    else:
        for branch in branches:
            console.print(
                f"Branch {branch.branch_id}: {len(branch.frequencies_hz)} points, "
                f"f0 = {branch.frequencies_hz[0] / 1e9:.4f} GHz"
            )
        if crossings:
            console.print(f"\n[bold]{len(crossings)} crossings detected[/bold]")


# ── Phase 2: Field Integration ─────────────────────────────────────────

field_app = typer.Typer(no_args_is_help=True, help="Field analysis commands.")
app.add_typer(field_app, name="fields")


@field_app.command("inspect")
def fields_inspect(
    bundle: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    field_path: Annotated[str | None, typer.Option("--field")] = None,
) -> None:
    """Inspect field metadata and statistics."""
    manifest = HFSSRunManifest.model_validate_json(
        (bundle / "manifest.json").read_text(encoding="utf-8")
    )
    for field in manifest.fields:
        if field_path and field_path not in str(field.path):
            continue
        console.print(
            f"[bold]{field.quantity}[/bold] mode={field.mode} "
            f"f={field.frequency_hz} shape={field.shape} "
            f"norm={field.normalization.value} rep={field.representation.value}"
        )


@field_app.command("integrate")
def fields_integrate(
    bundle: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    mode: Annotated[int | None, typer.Option("--mode")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Integrate field energies from a bundle."""
    results = integrate_bundle_fields(bundle, mode=mode)
    if json_output:
        typer.echo(json.dumps([r.model_dump(mode="json") for r in results], indent=2))
    else:
        for r in results:
            console.print(
                f"[bold]{r.region}[/bold]: U={r.total_energy_j:.3e} J, "
                f"V_eff={r.effective_mode_volume_m3:.3e} m^3, "
                f"imbalance={r.energy_imbalance:.4f}"
            )


@field_app.command("normalize")
def fields_normalize(
    bundle: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    mode: Annotated[int, typer.Option("--mode")] = 1,
    energy_convention: Annotated[str, typer.Option("--energy")] = "zero-point",
) -> None:
    """Report the normalization factor to reach a target energy convention."""
    from qresaudit.analysis.field_integration import ONE_PHOTON_ENERGY, ZERO_POINT_ENERGY

    manifest = HFSSRunManifest.model_validate_json(
        (bundle / "manifest.json").read_text(encoding="utf-8")
    )
    e_recs = [f for f in manifest.fields if f.quantity == "E" and f.mode == mode]
    if not e_recs:
        console.print("[red]No E-field found for mode {mode}[/red]")
        raise typer.Exit(1)
    freq = e_recs[0].frequency_hz or 0.0
    omega = 2.0 * 3.141592653589793 * freq
    targets = {
        "zero-point": ZERO_POINT_ENERGY(omega),
        "one-photon": ONE_PHOTON_ENERGY(omega),
    }
    target = targets.get(energy_convention, targets["zero-point"])
    results = integrate_bundle_fields(bundle, mode=mode)
    for r in results:
        alpha = (target / (r.total_energy_j + 1e-30)) ** 0.5
        alpha_str = f"{r.region}: alpha = {alpha:.6e}"
        console.print(f"{alpha_str} -> target {target:.3e} J ({energy_convention})")


# ── Phase 2: Participation ─────────────────────────────────────────────


@app.command()
def participation(
    bundle: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    regions: Annotated[Path | None, typer.Option("--regions", exists=True)] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Compute volume participation ratios and loss estimates."""
    _, loss = compute_participation_bundle(bundle, regions)
    if json_output:
        typer.echo(json.dumps(loss.model_dump(mode="json"), indent=2, default=str))
    else:
        console.print(f"[bold]Q_loss:[/bold] {loss.total_q_loss or 'N/A'}")
        console.print(f"[bold]Q_dielectric:[/bold] {loss.dielectric_q or 'N/A'}")
        console.print(f"[bold]Sum check:[/bold] {loss.sum_check:.4f}")
        for p in loss.per_region:
            console.print(
                f"  {p.region}: p_e={p.electric_participation:.4f}, "
                f"p_m={p.magnetic_participation:.4f}, "
                f"Q_contrib={p.estimated_q_contribution or 'N/A'}"
            )


@app.command()
def loss_estimate(
    bundle: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    materials: Annotated[Path | None, typer.Option("--materials", exists=True)] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Estimate Q_loss from materials and field participation."""
    _, loss = compute_participation_bundle(bundle, materials or None)
    if json_output:
        typer.echo(json.dumps(loss.model_dump(mode="json"), indent=2, default=str))
    else:
        console.print(f"Q_total_loss = {loss.total_q_loss or 'N/A'}")
        console.print(f"tanδ_eff = {loss.total_tan_delta}")


# ── Phase 2: Bundle Comparison ─────────────────────────────────────────


@app.command()
def compare(
    bundle_a: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    bundle_b: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Compare two validated bundles."""
    result = compare_bundles(bundle_a, bundle_b)
    if json_output:
        typer.echo(json.dumps(result.model_dump(mode="json"), indent=2, default=str))
    else:
        console.print(f"[bold]Classification:[/bold] {result.classification}")
        console.print(f"S-param RMS diff: {result.s_parameter_rms_difference}")
        console.print(f"S-param max diff: {result.s_parameter_max_difference}")
        if result.provenance_differences:
            console.print(f"Provenance diffs: {result.provenance_differences}")
        if result.variable_differences:
            console.print(f"Variable diffs: {result.variable_differences}")


# ── Phase 2: Audit Report ──────────────────────────────────────────────


@app.command()
def audit(
    bundle: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("audit"),
    regions: Annotated[Path | None, typer.Option("--regions", exists=True)] = None,
    fit_model: Annotated[str, typer.Option("--fit-model")] = "notch",
) -> None:
    """Generate a full audit report (HTML, JSON, Markdown, CSV)."""
    report = audit_bundle(bundle, regions_path=regions, fit_model=fit_model)
    write_audit_output(report, output)
    n_pass = sum(1 for v in report.verdicts if v.result == "PASS")
    n_fail = sum(1 for v in report.verdicts if v.result == "FAIL")
    n_warn = sum(1 for v in report.verdicts if v.result == "WARNING")
    console.print(f"[green]Audit complete: {n_pass} PASS, {n_warn} WARN, {n_fail} FAIL[/green]")
    console.print(f"Report: {output.resolve()}")


# ── Phase 5: Spin-Resonator Physics ────────────────────────────────────

spin_app = typer.Typer(no_args_is_help=True, help="Spin-resonator physics analysis.")
app.add_typer(spin_app, name="spin")


@spin_app.command("analyze")
def spin_analyze(
    bundle: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    ensemble: Annotated[Path | None, typer.Option("--ensemble", exists=True)] = None,
    mode: Annotated[int, typer.Option("--mode")] = 1,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Analyze spin-resonator coupling from a bundle."""
    if ensemble:
        import yaml

        raw = yaml.safe_load(ensemble.read_text(encoding="utf-8"))
        sample = SpinSampleConfig.model_validate(raw)
    else:
        sample = SpinSampleConfig()

    result = analyze_spin_coupling(bundle, sample, mode=mode)
    if json_output:
        typer.echo(json.dumps(result.model_dump(mode="json"), indent=2, default=str))
    else:
        console.print(f"[bold]g_eff:[/bold] {result.g_effective:.2f}")
        console.print(f"[bold]B1 ZPF (RMS):[/bold] {result.zero_point_b_field_rms_t:.3e} T")
        console.print(f"[bold]g_single:[/bold] {result.single_spin_coupling_hz:.3e} Hz")
        console.print(f"[bold]g_ens:[/bold] {result.ensemble_coupling_hz:.3e} Hz")
        console.print(f"[bold]Cooperativity:[/bold] {result.cooperativity:.3f}")
        console.print(f"[bold]Strong coupling:[/bold] {result.strong_coupling}")
        console.print(f"[bold]Filling factor:[/bold] {result.magnetic_filling_factor:.4f}")


@spin_app.command("sweep")
def spin_sweep(
    bundle: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    parameter: Annotated[str, typer.Option("--parameter", "-p")] = "orientation",
    start: Annotated[float, typer.Option("--start")] = 0.0,
    stop: Annotated[float, typer.Option("--stop")] = 360.0,
    steps: Annotated[int, typer.Option("--steps")] = 37,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Sweep a spin-sample parameter."""
    import numpy as np

    values = np.linspace(start, stop, steps).tolist()
    sample = SpinSampleConfig()
    result = sweep_parameter(bundle, sample, parameter, values)
    if json_output:
        typer.echo(json.dumps(result.model_dump(mode="json"), indent=2, default=str))
    else:
        console.print(f"Optimal {parameter}: {result.optimal_value}")
        console.print(f"Max coupling: {result.optimal_coupling_hz:.3e} Hz")
        console.print(f"Max cooperativity: {result.optimal_cooperativity:.3f}")


# ── Phase 6: Optimization ──────────────────────────────────────────────

optimize_app = typer.Typer(no_args_is_help=True, help="Design optimization commands.")
app.add_typer(optimize_app, name="optimize")


@optimize_app.command("sweep")
def optimize_sweep(
    bundle_dir: Annotated[Path, typer.Argument(exists=True, file_okay=False)],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Ingest a sweep directory and compute Pareto front."""
    console.print("[yellow]Sweep ingestion requires explicit objective definitions.[/yellow]")
    console.print(f"Sweep directory: {bundle_dir.resolve()}")


@optimize_app.command("bayesian")
def optimize_bayesian(
    config: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    iterations: Annotated[int, typer.Option("--iterations", "-n")] = 100,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Run Bayesian optimization from a config file."""
    import yaml

    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    from qresaudit.models.v0_2 import OptimizationObjective

    obj = OptimizationObjective.model_validate(raw.get("objective", {}))
    variables = {k: tuple(v) for k, v in raw.get("variables", {}).items()}
    result = bayesian_optimization(obj, variables, n_iterations=iterations)
    if json_output:
        typer.echo(json.dumps(result.model_dump(mode="json"), indent=2, default=str))
    else:
        if result.best_candidate:
            console.print(f"[bold]Best:[/bold] {result.best_candidate.objectives}")
            console.print(f"Variables: {result.best_candidate.variables}")
        console.print(f"Evaluations: {result.evaluations}")
        console.print(f"Pareto front size: {len(result.pareto_front)}")


@app.command("plan")
def plan_command(prompt: Annotated[str, typer.Argument()]) -> None:
    """Create a deterministic rule-based design plan; no LLM or solver is run."""
    typer.echo(json.dumps(asdict(plan_design(prompt)), indent=2))


@app.command("design-spec")
def design_spec_command(
    name: Annotated[str, typer.Option()],
    frequency_hz: Annotated[float, typer.Option()],
    output: Annotated[Path, typer.Option("--output", "-o")],
    center_width_m: Annotated[float, typer.Option()] = 10e-6,
    gap_m: Annotated[float, typer.Option()] = 6e-6,
    effective_permittivity: Annotated[float, typer.Option()] = 6.0,
) -> None:
    """Write a validated, solver-neutral quarter-wave CPW design specification."""
    design = make_cpw_design(
        name,
        frequency_hz,
        center_width_m=center_width_m,
        gap_m=gap_m,
        effective_permittivity=effective_permittivity,
    )
    write_portable_spec(design, str(output))
    typer.echo(str(output.resolve()))


@app.command("calibrate")
def calibrate_command(
    simulated: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    measured: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
) -> None:
    """Calibrate frequency/Q corrections from caller-supplied JSON evidence."""
    simulation_data = json.loads(simulated.read_text(encoding="utf-8"))
    measurement_data = json.loads(measured.read_text(encoding="utf-8"))
    result = calibrate_resonator(simulation_data, measurement_data)
    typer.echo(json.dumps(asdict(result), indent=2, sort_keys=True))


@app.command("knowledge-query")
def knowledge_query_command(
    database: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    text: Annotated[str, typer.Option()] = "",
    kind: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Query caller-supplied literature/material records without inventing citations."""
    knowledge = KnowledgeBase.from_json(database.read_text(encoding="utf-8"))
    typer.echo(json.dumps([asdict(item) for item in knowledge.query(text, kind=kind)], indent=2))


@app.command("research-report")
def research_report_command(
    design: Annotated[Path, typer.Option(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", "-o")],
    title: Annotated[str, typer.Option()] = "QResAudit design report",
    evidence: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
) -> None:
    """Build a reproducible report from explicit design and optional evidence JSON."""
    design_data = json.loads(design.read_text(encoding="utf-8"))
    evidence_data = (
        json.loads(evidence.read_text(encoding="utf-8")) if evidence is not None else None
    )
    report = build_design_report(title, design_data, evidence=evidence_data)
    write_design_report(report, output)
    typer.echo(str(output.resolve()))


@app.command("multiphysics")
def multiphysics_command(
    frequency_hz: Annotated[float, typer.Option()],
    temperature_delta_k: Annotated[float, typer.Option()] = 0.0,
    tempco_per_k: Annotated[float, typer.Option()] = 0.0,
    strain: Annotated[float, typer.Option()] = 0.0,
    gauge_factor: Annotated[float, typer.Option()] = 0.0,
) -> None:
    """Evaluate transparent first-order thermal and strain perturbations."""
    result = [
        thermal_frequency_shift(frequency_hz, temperature_delta_k, tempco_per_k).__dict__,
        strain_frequency_shift(frequency_hz, strain, gauge_factor).__dict__,
    ]
    typer.echo(json.dumps(result, indent=2))


@app.command("loop-dry-run")
def loop_dry_run(
    checkpoint: Annotated[Path, typer.Argument()], steps: Annotated[int, typer.Option()] = 2
) -> None:
    """Advance an offline loop without external solver/HPC execution."""
    if steps < 1:
        raise typer.BadParameter("steps must be positive")
    loop = SimulationLoop(checkpoint, budget=1, allow_external=False)
    for _ in range(steps):
        loop.dry_run_step()
    typer.echo(json.dumps(loop.state.__dict__, indent=2))
