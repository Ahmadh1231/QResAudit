from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from qresaudit.io.field_tab import parse_field_tab
from qresaudit.io.fields_hdf5 import source_metadata, write_field_hdf5
from qresaudit.models.common import Diagnostic, FieldRepresentation, NormalizationKind, error
from qresaudit.models.manifest import EigenmodeRecord, FieldRecord, FileRecord, TouchstoneRecord
from qresaudit.units import canonical_variation, unit_factor
from qresaudit_hfss.adapters.common import evidence_records, file_record
from qresaudit_hfss.adapters.driven import _evidence_capability_diagnostics
from qresaudit_hfss.exports.fields import export_field
from qresaudit_hfss.inspect import (
    field_grid_axes,
    field_grid_shape,
    field_source_coordinate_units,
)


class EigenmodeAdapter:
    def __init__(self, app: Any, config: Any, capabilities: Any) -> None:
        self.app, self.config, self.capabilities = app, config, capabilities
        self.solution_reference = f"{config.solution.setup} : LastAdaptive"
        self.mode_frequencies: dict[int, float] = {}

    def preflight(self) -> list[Diagnostic]:
        diagnostics = _evidence_capability_diagnostics(self.config, self.capabilities)
        if self.config.fields and not self.capabilities.has_fields_calculator_export:
            diagnostics.append(error("HFSS_CAPABILITY_FIELD_EXPORT_MISSING", "fields_calculator"))
        return diagnostics

    def _mode_data(self) -> pd.DataFrame:
        expressions = ["Eigenmode(Real)", "Eigenmode(Imag)", "Q"]
        data = self.app.post.get_solution_data(
            expressions=expressions,
            setup_sweep_name=self.solution_reference,
            domain="Sweep",
            variations=self.config.solution.variation,
        )
        if not data:
            raise ValueError("EXPORT_EIGENMODE_DATA_FAILED")
        modes = np.asarray(data.primary_sweep_values, dtype=int)
        units_data = getattr(data, "units_data", {})
        frequency_unit = units_data.get(expressions[0]) if isinstance(units_data, dict) else None
        if not frequency_unit:
            raise ValueError("EXPORT_EIGENMODE_FREQUENCY_UNIT_MISSING")
        frequency_scale = unit_factor(str(frequency_unit))
        real = np.asarray(data.data_real(expressions[0]), dtype=float) * frequency_scale
        try:
            imag_values = np.asarray(data.data_real(expressions[1]), dtype=float)
            imag: list[float | None] = [float(value * frequency_scale) for value in imag_values]
        except Exception:
            imag = [None] * len(real)
        try:
            q_values: list[float | None] = [
                float(value) for value in np.asarray(data.data_real(expressions[2]), dtype=float)
            ]
        except Exception:
            q_values = [None] * len(real)
        self.mode_frequencies = {
            int(mode): float(frequency) for mode, frequency in zip(modes, real, strict=True)
        }
        return pd.DataFrame(
            {
                "mode": modes,
                "frequency_real_hz": real,
                "frequency_imag_hz": imag,
                "q_hfss_unloaded": q_values,
                "source_solution": self.solution_reference,
                "variation_id": canonical_variation(self.config.solution.variation) or "nominal",
            }
        )

    def export_primary_results(
        self, staging: Path
    ) -> tuple[list[FileRecord], TouchstoneRecord | None, EigenmodeRecord | None]:
        modes = self._mode_data()
        target = staging / "modes" / "eigenmodes.csv"
        modes.to_csv(target, index=False)
        return (
            [file_record(target, staging, "eigenmodes", True)],
            None,
            EigenmodeRecord(path="modes/eigenmodes.csv", mode_count=len(modes)),
        )

    def export_evidence(self, staging: Path) -> list[FileRecord]:
        return evidence_records(self.app, self.config, staging)

    def export_fields(self, staging: Path) -> tuple[list[FileRecord], list[FieldRecord]]:
        files: list[FileRecord] = []
        fields: list[FieldRecord] = []
        for mode in self.config.solution.modes:
            frequency = self.mode_frequencies[mode]
            for field in self.config.fields:
                raw = (
                    staging
                    / "fields"
                    / "raw"
                    / f"mode_{mode:02d}_{field.quantity}_{field.name}.fld"
                )
                exported = export_field(
                    self.app,
                    field,
                    self.solution_reference,
                    self.config.solution.variation,
                    raw,
                    {"Mode": str(mode), "Phase": f"{field.phase_deg or 0}deg"},
                )
                parsed = parse_field_tab(
                    exported,
                    quantity=field.quantity,
                    value_units=field.value_units,
                    coordinate_units=field_source_coordinate_units(
                        field,
                        str(self.app.modeler.model_units),
                    ),
                )
                h5 = (
                    staging
                    / "fields"
                    / "hdf5"
                    / f"mode_{mode:02d}_{field.quantity}_{field.name}.h5"
                )
                normalization = NormalizationKind.HFSS_EIGENMODE_PEAK_1
                metadata = {
                    "grid_type": field.grid.type.value,
                    "topology": "unstructured"
                    if field.grid.sample_points_file is not None
                    else "structured",
                    "shape": field_grid_shape(field) or [len(parsed.coordinates_m)],
                    "axes": field_grid_axes(field),
                    "axis_order": ["x", "y", "z"],
                    "flattening_order": "C",
                    "coordinate_system": field.reference_coordinate_system,
                    "solution_reference": self.solution_reference,
                    "setup_name": self.config.solution.setup,
                    "mode": mode,
                    "frequency_hz": frequency,
                    "phase_deg": field.phase_deg,
                    "representation": (
                        field.representation.value
                        if field.representation is not None
                        else ("complex_phasor" if parsed.is_complex else "real_gauge")
                    ),
                    "phasor_convention": field.phasor_convention.value,
                    "normalization": normalization.value,
                    "region_name": field.name,
                    "assignments_json": field.assignment,
                    **source_metadata(exported),
                }
                write_field_hdf5(h5, parsed, metadata)
                files.extend(
                    [
                        file_record(exported, staging, "field_raw", True),
                        file_record(
                            h5,
                            staging,
                            "field_hdf5",
                            True,
                            source_path=exported.relative_to(staging).as_posix(),
                        ),
                    ]
                )
                fields.append(
                    FieldRecord(
                        path=h5.relative_to(staging).as_posix(),
                        raw_path=exported.relative_to(staging).as_posix(),
                        quantity=field.quantity,
                        complex_data=parsed.is_complex,
                        vector=parsed.is_vector,
                        units=parsed.value_units,
                        coordinate_units="m",
                        coordinate_system=field.reference_coordinate_system,
                        grid_type=field.grid.type.value,
                        region_name=field.name,
                        assignment=field.assignment,
                        object_type=field.object_type.value,
                        solution=self.solution_reference,
                        mode=mode,
                        frequency_hz=frequency,
                        phase_deg=field.phase_deg,
                        normalization=normalization,
                        shape=[
                            *(metadata["shape"]),
                            *([3] if parsed.is_vector else []),
                        ],
                        point_count=len(parsed.coordinates_m),
                        representation=(
                            field.representation
                            if field.representation is not None
                            else (
                                FieldRepresentation.COMPLEX_PHASOR
                                if parsed.is_complex
                                else FieldRepresentation.REAL_GAUGE
                            )
                        ),
                        phasor_convention=field.phasor_convention,
                        component_labels=["x", "y", "z"] if parsed.is_vector else ["scalar"],
                        topology=metadata["topology"],
                        variation=self.config.solution.variation,
                    )
                )
        return files, fields
