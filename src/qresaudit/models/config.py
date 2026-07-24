import math
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from qresaudit.models.common import EvidenceProfile, FieldRepresentation, PhasorConvention
from qresaudit.units import field_quantity_contract


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GridType(StrEnum):
    CARTESIAN = "Cartesian"
    CYLINDRICAL = "Cylindrical"
    SPHERICAL = "Spherical"


class AssignmentType(StrEnum):
    VOLUME = "Vol"
    SURFACE = "Surf"
    LINE = "Line"


class AngularUnit(StrEnum):
    DEGREES = "deg"
    RADIANS = "rad"


class ProjectConfig(StrictModel):
    path: Path
    design: str
    aedt_version: str | None = None
    non_graphical: bool = True
    student_version: bool = False
    remove_lock: bool = False
    attach_process_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def student_uses_graphical_mode(self) -> "ProjectConfig":
        if self.student_version and self.non_graphical:
            raise ValueError("Student AEDT does not support non-graphical batch mode")
        if self.remove_lock:
            raise ValueError("remove_lock is forbidden for read-only inspection/export")
        return self


class SolutionConfig(StrictModel):
    setup: str
    sweep: str | None = None
    variation: dict[str, str] = Field(default_factory=dict)
    modes: list[int] = Field(default_factory=lambda: [1])

    @model_validator(mode="after")
    def validate_modes(self) -> "SolutionConfig":
        if any(mode <= 0 for mode in self.modes):
            raise ValueError("mode numbers must be positive")
        if len(set(self.modes)) != len(self.modes):
            raise ValueError("mode numbers must be unique")
        return self


class TouchstoneConfig(StrictModel):
    enabled: bool = True
    renormalize: bool = False
    impedance_ohm: float | None = Field(default=None, gt=0)
    include_gamma_impedance_comments: bool = True

    @model_validator(mode="after")
    def validate_impedance(self) -> "TouchstoneConfig":
        if self.renormalize and self.impedance_ohm is None:
            raise ValueError("impedance_ohm is required when renormalize is true")
        return self


class FieldGridConfig(StrictModel):
    type: GridType = GridType.CARTESIAN
    start: list[str] | None = None
    stop: list[str] | None = None
    step: list[str] | None = None
    center: list[str] | None = None
    sample_points_file: Path | None = None

    @model_validator(mode="after")
    def one_grid_mode(self) -> "FieldGridConfig":
        has_grid = any(
            value is not None for value in (self.start, self.stop, self.step, self.center)
        )
        if self.sample_points_file is not None and has_grid:
            raise ValueError("define sample_points_file or a grid, not both")
        if self.center is not None:
            if len(self.center) != 3:
                raise ValueError("grid center must contain exactly three values")
            for value in self.center:
                self._finite_quantity(value, "center")
        if self.sample_points_file is None:
            if self.start is None or self.stop is None or self.step is None:
                raise ValueError("grid start, stop, and step are required")
            for name, values in (("start", self.start), ("stop", self.stop), ("step", self.step)):
                if len(values) != 3:
                    raise ValueError(f"grid {name} must contain exactly three values")
            starts = [self._finite_quantity(v, "start") for v in self.start]
            stops = [self._finite_quantity(v, "stop") for v in self.stop]
            steps = [self._finite_quantity(v, "step") for v in self.step]
            for index, (start, stop, step) in enumerate(zip(starts, stops, steps, strict=True)):
                if not start <= stop:
                    raise ValueError(f"grid stop must be >= start on axis {index}")
                if step <= 0:
                    raise ValueError(f"grid step must be finite and positive on axis {index}")
        elif not self.sample_points_file.is_file():
            raise ValueError("sample_points_file must be an existing file")
        else:
            rows = []
            for line_number, line in enumerate(
                self.sample_points_file.read_text(encoding="utf-8").splitlines(), 1
            ):
                if not line.strip() or line.lstrip().startswith(("#", "!", "%")):
                    continue
                tokens = line.replace(",", " ").split()
                if len(tokens) != 3:
                    raise ValueError(f"sample point line {line_number} must have three values")
                rows.append(tuple(self._finite_quantity(token, "sample point") for token in tokens))
            if not rows:
                raise ValueError("sample_points_file contains no points")
            if len(set(rows)) != len(rows):
                raise ValueError("sample_points_file contains duplicate points")
        return self

    @staticmethod
    def _finite_quantity(value: str, label: str) -> float:
        from qresaudit.units import convert_to_si

        result = convert_to_si(value)
        if not math.isfinite(result):
            raise ValueError(f"{label} must be finite")
        return result


class FieldExportConfig(StrictModel):
    name: str = Field(pattern=r"^[A-Za-z0-9_]+$")
    quantity: str
    vector: bool = True
    value_units: str | None = None
    assignment: list[str] = Field(default_factory=lambda: ["AllObjects"])
    object_type: AssignmentType = AssignmentType.VOLUME
    reference_coordinate_system: str = "Global"
    export_in_si_system: bool = True
    export_field_in_reference: bool = True
    grid: FieldGridConfig
    phase_deg: float | None = 0.0
    phase_unit: AngularUnit = AngularUnit.DEGREES
    frequency_hz: float | None = Field(default=None, gt=0)
    excitation: str | None = None
    coordinate_units: str | None = None
    representation: FieldRepresentation | None = None
    phasor_convention: PhasorConvention = PhasorConvention.UNKNOWN

    @model_validator(mode="after")
    def phase_is_finite(self) -> "FieldExportConfig":
        if self.phase_deg is not None and not math.isfinite(self.phase_deg):
            raise ValueError("phase must be finite")
        canonical, vector, units = field_quantity_contract(
            self.quantity,
            vector=self.vector,
            explicit_units=self.value_units,
        )
        self.quantity = canonical
        self.vector = vector
        self.value_units = units
        return self


class ExportConfig(StrictModel):
    schema_version: str = "0.1.1"
    project: ProjectConfig
    solution: SolutionConfig
    evidence_profile: EvidenceProfile = EvidenceProfile.STANDARD
    touchstone: TouchstoneConfig = Field(default_factory=TouchstoneConfig)
    fields: list[FieldExportConfig] = Field(default_factory=list)
    export_existing_reports: bool = True
    report_names: list[str] = Field(default_factory=list)
    export_convergence: bool = True
    export_mesh_stats: bool = True
    export_profile: bool = True
    export_mesh_visualization: bool = True
    keep_raw_exports: bool = True
    strict: bool = True
    keep_failed: bool = False
    portable_paths: bool = True
    max_field_points: int = Field(default=2_000_000, ge=1)

    @model_validator(mode="after")
    def evidence_profile_is_consistent(self) -> "ExportConfig":
        if self.evidence_profile in {
            EvidenceProfile.STANDARD,
            EvidenceProfile.STRICT,
        } and (not self.export_convergence or not self.export_mesh_stats):
            raise ValueError(
                "standard and strict evidence require convergence and mesh-statistics exports"
            )
        if self.evidence_profile is EvidenceProfile.STRICT and not self.fields:
            raise ValueError("strict evidence requires field exports")
        return self
