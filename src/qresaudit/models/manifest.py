from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from qresaudit.models.common import (
    Diagnostic,
    ExportStatus,
    NormalizationKind,
    SolutionKind,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FileRecord(StrictModel):
    path: str
    role: str
    media_type: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    required: bool
    source_path: str | None = None
    generated_by: str | None = None


class SoftwareRecord(StrictModel):
    name: str
    version: str


class VariationValue(StrictModel):
    expression: str
    evaluated_value: float | None = None
    evaluated_unit: str | None = None


class TouchstoneRecord(StrictModel):
    path: str
    number_of_ports: int = Field(ge=1)
    frequency_unit: str
    parameter_type: str = "S"
    data_format: str
    renormalized: bool
    reference_impedance_ohm: float | None = None
    port_names: list[str]
    frequency_min_hz: float
    frequency_max_hz: float
    point_count: int = Field(ge=1)


class EigenmodeRecord(StrictModel):
    path: str
    mode_count: int = Field(ge=1)
    frequency_unit: str = "Hz"
    q_definition: str = "hfss_unloaded_material_and_boundary_loss"


class FieldRecord(StrictModel):
    path: str
    raw_path: str
    quantity: str
    complex_data: bool
    vector: bool
    units: str
    coordinate_units: str
    coordinate_system: str
    grid_type: str
    region_name: str
    assignment: list[str]
    object_type: str
    solution: str
    mode: int | None = None
    frequency_hz: float | None = None
    phase_deg: float | None = None
    normalization: NormalizationKind
    shape: list[int]
    point_count: int = Field(ge=1)


class HFSSRunManifest(StrictModel):
    schema_version: str = "0.1.0"
    exporter_version: str
    bundle_status: ExportStatus
    run_id: str = Field(pattern=r"^[0-9a-f]{8}$")
    export_timestamp_utc: datetime
    project_name: str
    project_file_name: str
    project_file_sha256: str | None
    design_name: str
    design_type: str
    solution_kind: SolutionKind
    setup_name: str
    sweep_name: str | None
    solution_reference: str
    variation_id: str
    variation: dict[str, VariationValue]
    aedt_version: str
    pyaedt_version: str
    python_version: str
    operating_system: str
    model_units: str
    reference_coordinate_system: str
    ports: list[str]
    touchstone: TouchstoneRecord | None
    eigenmode: EigenmodeRecord | None
    fields: list[FieldRecord]
    files: list[FileRecord]
    diagnostics: list[Diagnostic]
