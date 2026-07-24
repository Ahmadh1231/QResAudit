from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectConfig(StrictModel):
    path: Path
    design: str
    aedt_version: str | None = None
    non_graphical: bool = True
    student_version: bool = False
    remove_lock: bool = False

    @model_validator(mode="after")
    def student_uses_graphical_mode(self) -> "ProjectConfig":
        if self.student_version and self.non_graphical:
            raise ValueError("Student AEDT does not support non-graphical batch mode")
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
    type: str = "Cartesian"
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
        if self.sample_points_file is None:
            if self.start is None or self.stop is None or self.step is None:
                raise ValueError("grid start, stop, and step are required")
            for name, values in (("start", self.start), ("stop", self.stop), ("step", self.step)):
                if len(values) != 3:
                    raise ValueError(f"grid {name} must contain exactly three values")
        return self


class FieldExportConfig(StrictModel):
    name: str = Field(pattern=r"^[A-Za-z0-9_]+$")
    quantity: str
    vector: bool = True
    assignment: list[str] = Field(default_factory=lambda: ["AllObjects"])
    object_type: str = "Vol"
    reference_coordinate_system: str = "Global"
    export_in_si_system: bool = True
    export_field_in_reference: bool = True
    grid: FieldGridConfig
    phase_deg: float | None = 0.0


class ExportConfig(StrictModel):
    schema_version: str = "0.1.0"
    project: ProjectConfig
    solution: SolutionConfig
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
