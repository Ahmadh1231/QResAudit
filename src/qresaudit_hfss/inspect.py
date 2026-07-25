from contextlib import suppress
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from qresaudit.models.common import Diagnostic, SolutionKind, error, warning
from qresaudit.models.config import ExportConfig
from qresaudit.units import (
    RECOGNIZED_COORDINATE_UNITS,
    canonical_variation,
    convert_to_si,
    parse_quantity,
)


class DesignInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_name: str
    design_name: str
    design_type: str
    solution_type_raw: str
    solution_kind: SolutionKind | None
    model_units: str
    setups: list[str]
    setup_sweeps: list[str]
    existing_analysis_sweeps: list[str]
    available_variations: list[dict[str, str]]
    reports: list[str]
    ports: list[str]
    excitations: list[str]
    project_variables: dict[str, str]
    design_variables: dict[str, str]
    solved: bool = False
    modes_available: int | None = None
    object_names: list[str] = Field(default_factory=list)
    warnings: list[Diagnostic] = Field(default_factory=list)


def map_solution_kind(value: str) -> SolutionKind | None:
    normalized = value.lower().replace(" ", "").replace("_", "")
    # PyAEDT reports either the descriptive AEDT names or the shortened
    # ``Modal``/``Terminal`` values depending on its version and backend.
    if normalized in {"modal", "drivenmodal"}:
        return SolutionKind.DRIVEN_MODAL
    if normalized in {"terminal", "driventerminal"}:
        return SolutionKind.DRIVEN_TERMINAL
    if normalized == "eigenmode":
        return SolutionKind.EIGENMODE
    return None


def _variable_dict(manager: Any) -> tuple[dict[str, str], dict[str, str]]:
    project: dict[str, str] = {}
    design: dict[str, str] = {}
    for name in getattr(manager, "variable_names", []):
        try:
            expression = str(manager[name].expression)
        except Exception:
            expression = str(manager[name])
        (project if str(name).startswith("$") else design)[str(name)] = expression
    return project, design


def inspect_design(app: Any) -> DesignInspection:
    solution_type = str(getattr(app, "solution_type", ""))
    project_variables, design_variables = _variable_dict(app.variable_manager)
    setup_names = [str(value) for value in getattr(app, "setup_names", [])]
    sweeps = [str(value) for value in getattr(app, "existing_analysis_sweeps", [])]
    reports = [str(value) for value in getattr(app.post, "all_report_names", [])]
    excitations = [str(value) for value in getattr(app, "excitation_names", [])]
    ports = [value for value in excitations if value]
    inspection_warnings: list[Diagnostic] = []
    available_variations: list[dict[str, str]] = []
    try:
        raw_variations: set[str] = set()
        for reference in sweeps:
            setup, separator, sweep = reference.partition(":")
            if not separator:
                continue
            raw_variations.update(
                str(value)
                for value in app.list_of_variations(setup=setup.strip(), sweep=sweep.strip())
                if str(value).strip()
            )
        available_variations = [{"raw": value} for value in sorted(raw_variations)]
    except Exception as exc:
        inspection_warnings.append(
            warning(
                "HFSS_VARIATIONS_UNAVAILABLE",
                "Solved variations could not be enumerated",
                detail=str(exc),
            )
        )
    object_names: list[str] = []
    model_units = ""
    try:
        modeler = app.modeler
        object_names = [str(value) for value in getattr(modeler, "object_names", [])]
        model_units = str(getattr(modeler, "model_units", ""))
    except Exception as exc:
        inspection_warnings.append(
            warning(
                "HFSS_MODELER_INSPECTION_UNAVAILABLE",
                "Modeler metadata could not be enumerated",
                detail=str(exc),
            )
        )
    solved = bool(sweeps)
    modes_available = None
    if map_solution_kind(solution_type) is SolutionKind.EIGENMODE:
        with suppress(Exception):
            modes_available = int(app.get_setup(setup_names[0]).props.get("NumModes", 0))
    return DesignInspection(
        project_name=str(getattr(app, "project_name", "")),
        design_name=str(getattr(app, "design_name", "")),
        design_type=str(getattr(app, "design_type", "HFSS")),
        solution_type_raw=solution_type,
        solution_kind=map_solution_kind(solution_type),
        model_units=model_units,
        setups=setup_names,
        setup_sweeps=sweeps,
        existing_analysis_sweeps=sweeps,
        available_variations=available_variations,
        reports=reports,
        ports=ports,
        excitations=excitations,
        project_variables=project_variables,
        design_variables=design_variables,
        solved=solved,
        modes_available=modes_available,
        object_names=object_names,
        warnings=inspection_warnings,
    )


def axis_count(start: float, stop: float, step: float) -> int:
    if not (step > 0 and stop >= start):
        raise ValueError("invalid grid axis")
    return round((stop - start) / step) + 1


def field_grid_shape(field: Any) -> list[int] | None:
    if field.grid.sample_points_file is not None:
        return None
    starts = [convert_to_si(value) for value in field.grid.start]
    stops = [convert_to_si(value) for value in field.grid.stop]
    steps = [convert_to_si(value) for value in field.grid.step]
    return [
        axis_count(start, stop, step)
        for start, stop, step in zip(starts, stops, steps, strict=True)
    ]


def field_grid_axes(field: Any) -> dict[str, list[float]]:
    shape = field_grid_shape(field)
    if shape is None:
        return {}
    starts = [convert_to_si(value) for value in field.grid.start]
    steps = [convert_to_si(value) for value in field.grid.step]
    return {
        axis: [start + index * step for index in range(count)]
        for axis, start, step, count in zip(("x", "y", "z"), starts, steps, shape, strict=True)
    }


def field_source_coordinate_units(field: Any, model_units: str) -> str:
    if field.coordinate_units is not None:
        return str(field.coordinate_units)
    units: set[str] = set()
    for values in (field.grid.start, field.grid.stop, field.grid.step):
        if values is not None:
            units.update(parse_quantity(value)[1] for value in values)
    if len(units) == 1:
        return units.pop()
    if model_units in RECOGNIZED_COORDINATE_UNITS:
        return model_units
    raise ValueError("field output coordinate units are ambiguous; set coordinate_units explicitly")


def field_grid_point_count(field: Any) -> int | None:
    if field.grid.sample_points_file is not None:
        path = Path(field.grid.sample_points_file)
        return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    counts = field_grid_shape(field)
    if counts is None:
        raise ValueError("field grid shape is unavailable")
    return counts[0] * counts[1] * counts[2]


def canonical_solution_reference(setup: str, sweep: str | None) -> str:
    return f"{setup} : {sweep or 'LastAdaptive'}"


def run_preflight(inspection: DesignInspection, config: ExportConfig) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    project = config.project.path
    if not project.is_file() or project.suffix.lower() not in {".aedt", ".aedtz"}:
        diagnostics.append(
            error(
                "HFSS_PROJECT_OPEN_FAILED", "Project path must be an existing .aedt or .aedtz file"
            )
        )
    if inspection.design_name != config.project.design:
        diagnostics.append(error("HFSS_DESIGN_NOT_FOUND", "Requested design is not active"))
    if inspection.design_type.upper() != "HFSS":
        diagnostics.append(error("HFSS_UNSUPPORTED_DESIGN_TYPE", "Design is not HFSS 3D"))
    if inspection.solution_kind is None:
        diagnostics.append(error("HFSS_UNSUPPORTED_SOLUTION_TYPE", inspection.solution_type_raw))
    if config.solution.setup not in inspection.setups:
        diagnostics.append(error("HFSS_SETUP_NOT_FOUND", config.solution.setup))
    expected_reference = canonical_solution_reference(
        config.solution.setup,
        config.solution.sweep
        if inspection.solution_kind in {SolutionKind.DRIVEN_MODAL, SolutionKind.DRIVEN_TERMINAL}
        else None,
    )
    available_references = {
        " : ".join(part.strip() for part in value.split(":", 1))
        for value in inspection.existing_analysis_sweeps
    }
    if inspection.solution_kind in {SolutionKind.DRIVEN_MODAL, SolutionKind.DRIVEN_TERMINAL}:
        if not inspection.excitations:
            diagnostics.append(error("HFSS_PORTS_NOT_FOUND", "Driven design has no excitations"))
        if not config.touchstone.enabled:
            diagnostics.append(
                error("HFSS_DRIVEN_TOUCHSTONE_REQUIRED", "Driven export requires network evidence")
            )
        if not config.solution.sweep:
            diagnostics.append(error("HFSS_SWEEP_NOT_FOUND", "Driven solution requires a sweep"))
        elif expected_reference not in available_references:
            diagnostics.append(error("HFSS_SWEEP_NOT_SOLVED", expected_reference))
    if inspection.solution_kind is SolutionKind.EIGENMODE:
        if config.touchstone.enabled:
            diagnostics.append(
                error("HFSS_EIGENMODE_TOUCHSTONE", "Touchstone must be disabled for eigenmode")
            )
        if inspection.modes_available is not None:
            for mode in config.solution.modes:
                if mode > inspection.modes_available:
                    diagnostics.append(
                        error("HFSS_MODE_NOT_SOLVED", f"Mode {mode} exceeds solved count")
                    )
    if not inspection.solved or expected_reference not in available_references:
        diagnostics.append(
            error(
                "HFSS_VARIATION_NOT_SOLVED",
                f"Exact solved solution was not discovered: {expected_reference}",
            )
        )
    for field in config.fields:
        try:
            count = field_grid_point_count(field)
            if count is not None and count > config.max_field_points:
                diagnostics.append(
                    error("HFSS_FIELD_GRID_TOO_LARGE", f"{field.name} requests {count:,} points")
                )
        except (OSError, ValueError) as exc:
            diagnostics.append(error("HFSS_FIELD_GRID_INVALID", str(exc)))
        missing = set(field.assignment) - set(inspection.object_names) - {"AllObjects"}
        if missing:
            diagnostics.append(error("HFSS_FIELD_ASSIGNMENT_NOT_FOUND", ", ".join(sorted(missing))))
    if config.solution.variation:
        canonical_variation(config.solution.variation)
    if inspection.solution_kind is SolutionKind.DRIVEN_TERMINAL:
        diagnostics.append(
            error(
                "HFSS_DRIVEN_TERMINAL_UNSUPPORTED",
                "Driven Terminal export is disabled until terminal/reference provenance is modeled",
            )
        )
    return diagnostics
